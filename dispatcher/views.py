import datetime
import urllib.parse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required  # <-- Add this line here
from django.contrib.auth.models import User
from django.utils import timezone
from .models import TimeSlot, TeamMember


DEFAULT_ADMIN_MOBILE = "01700000000"
DEFAULT_ADMIN_PASS = "Admin123!"

DEFAULT_DOCTORS_DATA = [
    ("Dr. Sarah Jenkins", "01711000001"),
    ("Dr. Marcus Chen", "01711000002"),
    ("Dr. Priya Patel", "01711000003"),
    ("Dr. Alexander Ross", "01711000004"),
]

DEFAULT_STAFF_DATA = [
    ("Receptionist Emily", "01712000001"),
    ("Receptionist Alex", "01712000002"),
    ("Receptionist Marcus", "01712000003"),
    ("Receptionist Clara", "01712000004"),
]

DEFAULT_DOCTORS = [d[0] for d in DEFAULT_DOCTORS_DATA]
DEFAULT_STAFF = [s[0] for s in DEFAULT_STAFF_DATA]


def ensure_default_team_members():
    """Ensure standard initial admin, doctors, and staff exist with auth accounts."""
    # 1. Ensure Default Admin Account
    admin_user = User.objects.filter(username=DEFAULT_ADMIN_MOBILE).first()
    if not admin_user:
        User.objects.create_user(
            username=DEFAULT_ADMIN_MOBILE,
            password=DEFAULT_ADMIN_PASS,
            first_name="Clinic Admin",
            is_staff=True,
            is_superuser=True
        )

    # 2. Ensure Default Doctors
    for doc_name, doc_phone in DEFAULT_DOCTORS_DATA:
        member = TeamMember.objects.filter(name=doc_name).first()
        if not member:
            user = User.objects.filter(username=doc_phone).first()
            if not user:
                user = User.objects.create_user(
                    username=doc_phone,
                    password="DoctorPass123!",
                    first_name=doc_name
                )
            TeamMember.objects.create(
                name=doc_name,
                role='doctor',
                phone_number=doc_phone,
                user=user,
                is_active=True
            )
        elif not member.phone_number:
            member.phone_number = doc_phone
            if not member.user:
                user = User.objects.filter(username=doc_phone).first()
                if not user:
                    user = User.objects.create_user(
                        username=doc_phone,
                        password="DoctorPass123!",
                        first_name=doc_name
                    )
                member.user = user
            member.save()

    # 3. Ensure Default Receptionists
    for staff_name, staff_phone in DEFAULT_STAFF_DATA:
        member = TeamMember.objects.filter(name=staff_name).first()
        if not member:
            user = User.objects.filter(username=staff_phone).first()
            if not user:
                user = User.objects.create_user(
                    username=staff_phone,
                    password="StaffPass123!",
                    first_name=staff_name
                )
            TeamMember.objects.create(
                name=staff_name,
                role='receptionist',
                phone_number=staff_phone,
                user=user,
                is_active=True
            )
        elif not member.phone_number:
            member.phone_number = staff_phone
            if not member.user:
                user = User.objects.filter(username=staff_phone).first()
                if not user:
                    user = User.objects.create_user(
                        username=staff_phone,
                        password="StaffPass123!",
                        first_name=staff_name
                    )
                member.user = user
            member.save()


def generate_full_day_15min_times():
    """
    Generates 15-minute intervals starting exactly at 8:00 AM (08:00:00)
    and running through Midnight (23:45:00) inclusive (64 slots).
    """
    times = []
    # 08:00 to 23:45 in 15-minute intervals
    for hour in range(8, 24):
        for minute in (0, 15, 30, 45):
            times.append(datetime.time(hour, minute))
    return times


def ensure_doctor_slots_exist(target_date, doctor_name):
    """Ensure standard full-day 15-minute slots exist for a given doctor and date."""
    times = generate_full_day_15min_times()
    slots_to_create = []

    # Check existing times for this doctor on this date
    existing_times = set(
        TimeSlot.objects.filter(date=target_date, doctor_name=doctor_name)
        .values_list('start_time', flat=True)
    )

    for t in times:
        if t not in existing_times:
            slots_to_create.append(
                TimeSlot(
                    date=target_date,
                    start_time=t,
                    doctor_name=doctor_name,
                    is_booked=False,
                )
            )

    if slots_to_create:
        TimeSlot.objects.bulk_create(slots_to_create)


@login_required(login_url='/')
def daily_calendar_view(request):
    """
    Multi-doctor, full-day calendar view with 15-minute intervals.
    Supports ?date=YYYY-MM-DD, ?doctor=Doctor+Name, and ?period=all|morning|afternoon|evening.
    """
    date_str = request.GET.get('date')
    if date_str:
        try:
            current_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            current_date = timezone.localdate()
    else:
        current_date = timezone.localdate()

    # Ensure team roster initialized
    ensure_default_team_members()

    # Active doctors for selector & quick-switch pills
    active_doctors = list(TeamMember.objects.filter(
        role='doctor', is_active=True).values_list(
        'name', flat=True))
    if not active_doctors:
        active_doctors = DEFAULT_DOCTORS

    # Get or default doctor
    doctor_name = request.GET.get('doctor', '').strip()
    if not doctor_name:
        doctor_name = active_doctors[0]

    # Time-of-day period filter (all, morning, afternoon, evening)
    period = request.GET.get('period', 'all').lower()

    # Ensure this doctor has the 15-min slots for current_date
    ensure_doctor_slots_exist(current_date, doctor_name)

    # Check if selected doctor is currently active or archived
    team_doc = TeamMember.objects.filter(
        name=doctor_name, role='doctor').first()
    if team_doc is None:
        # If a new doctor was manually entered, register them as active
        team_doc = TeamMember.objects.create(
            name=doctor_name, role='doctor', is_active=True)
        active_doctors.append(doctor_name)
    is_current_doctor_active = team_doc.is_active

    # Active receptionists for booking modal dropdown
    active_staff = list(TeamMember.objects.filter(
        role='receptionist', is_active=True).values_list(
        'name', flat=True))
    if not active_staff:
        active_staff = DEFAULT_STAFF

    # All doctors & receptionists for the Manage Team modal
    all_doctors = TeamMember.objects.filter(
        role='doctor').order_by(
        '-is_active', 'name')
    all_staff = TeamMember.objects.filter(
        role='receptionist').order_by(
        '-is_active', 'name')

    # Query slots
    all_doctor_slots = TimeSlot.objects.filter(
        date=current_date,
        doctor_name=doctor_name
    ).order_by('start_time')

    total_slots = all_doctor_slots.count()
    booked_slots = all_doctor_slots.filter(is_booked=True).count()
    available_slots = total_slots - booked_slots
    occupancy_rate = round(
        (booked_slots / total_slots * 100)) if total_slots > 0 else 0

    # Filter by period for UI display
    displayed_slots = all_doctor_slots
    if period == 'morning':
        displayed_slots = displayed_slots.filter(
            start_time__lt=datetime.time(12, 0))
    elif period == 'afternoon':
        displayed_slots = displayed_slots.filter(
            start_time__gte=datetime.time(12, 0),
            start_time__lt=datetime.time(17, 0)
        )
    elif period == 'evening':
        displayed_slots = displayed_slots.filter(
            start_time__gte=datetime.time(17, 0))

    prev_date = current_date - datetime.timedelta(days=1)
    next_date = current_date + datetime.timedelta(days=1)

    logged_in_staff_name = ""
    logged_in_user_display = ""
    if request.user.is_authenticated:
        if hasattr(request.user, 'team_profile') and request.user.team_profile:
            logged_in_staff_name = request.user.team_profile.name
        elif request.user.first_name:
            logged_in_staff_name = request.user.first_name
        elif request.user.get_full_name():
            logged_in_staff_name = request.user.get_full_name()
        else:
            logged_in_staff_name = request.user.username

        logged_in_user_display = request.user.first_name or request.user.get_full_name(
        ) or request.user.username

    context = {
        'slots': displayed_slots, 'current_date': current_date,
        'prev_date': prev_date, 'next_date': next_date,
        'today': timezone.localdate(),
        'selected_doctor': doctor_name, 'doctors_list': active_doctors,
        'active_doctors': active_doctors,
        'is_current_doctor_active': is_current_doctor_active,
        'staff_list': active_staff, 'all_doctors': all_doctors,
        'all_staff': all_staff, 'is_admin': request.user.is_authenticated
        and (request.user.is_staff or request.user.is_superuser),
        'logged_in_staff_name': logged_in_staff_name,
        'logged_in_user_display': logged_in_user_display,
        'default_admin_mobile': DEFAULT_ADMIN_MOBILE,
        'default_admin_pass': DEFAULT_ADMIN_PASS, 'period': period,
        'total_slots': total_slots, 'booked_slots': booked_slots,
        'available_slots': available_slots, 'occupancy_rate': occupancy_rate, }
    return render(request, 'dispatcher/daily_calendar.html', context)


@require_POST
def book_calendar_slot(request, slot_id=None):
    """
    Handles a POST request to update a specific slot's patient_name, patient_phone,
    booked_by, and receptionist_name and sets is_booked = True,
    then redirects back to the calendar view for that date & doctor.
    """
    if not slot_id:
        slot_id = request.POST.get('slot_id')

    slot = get_object_or_404(TimeSlot, pk=slot_id)
    patient_name = request.POST.get('patient_name', '').strip()
    patient_phone = request.POST.get('patient_phone', '').strip()
    booked_by = request.POST.get('booked_by', '').strip()

    # Smart Receptionist / Staff Intake:
    # a) Regular staff member: automatically locked to their own name
    # b) Admin / Superuser: full privilege to select any receptionist
    if request.user.is_authenticated and not (
            request.user.is_staff or request.user.is_superuser):
        if hasattr(request.user, 'team_profile') and request.user.team_profile:
            receptionist_name = request.user.team_profile.name
        elif request.user.first_name:
            receptionist_name = request.user.first_name
        elif request.user.get_full_name():
            receptionist_name = request.user.get_full_name()
        else:
            receptionist_name = "Staff Member"
    else:
        receptionist_name = request.POST.get('receptionist_name', '').strip()

    if not patient_name:
        messages.error(
            request, "Patient / Booking Person name cannot be empty.")
    elif not patient_phone:
        messages.error(
            request, "Patient phone number is required for call tracking.")
    elif slot.is_booked:
        messages.warning(
            request,
            f"Slot at {slot.start_time.strftime('%I:%M %p')} is already booked by {slot.patient_name}."
        )
    else:
        slot.patient_name = patient_name
        slot.patient_phone = patient_phone
        slot.booked_by = booked_by if booked_by else None
        slot.receptionist_name = receptionist_name if receptionist_name else None
        slot.is_booked = True
        slot.booked_at = timezone.now()
        slot.booked_by_user = request.user if request.user.is_authenticated else None
        slot.save()
        messages.success(
            request,
            f"Successfully booked {slot.start_time.strftime('%I:%M %p')} with {slot.doctor_name} for {patient_name}!"
        )

    redirect_url = f"/?date={
        slot.date.isoformat()} &doctor={
        urllib.parse.quote_plus(slot.doctor_name)} "
    return redirect(redirect_url)


@require_POST
def cancel_calendar_slot(request, slot_id):
    """
    Helper action to cancel a booking and return slot to available state.
    Restricted to the exact staff member whose login account created the booking,
    or an administrator / superuser.
    """
    slot = get_object_or_404(TimeSlot, pk=slot_id)
    user = request.user
    is_admin = user.is_authenticated and (user.is_staff or user.is_superuser)
    is_booking_owner = user.is_authenticated and (
        slot.booked_by_user_id == user.id)

    if not (is_admin or is_booking_owner):
        messages.error(
            request,
            "Permission denied. Only the staff member who created this booking or an administrator can release this slot."
        )
        redirect_url = f"/?date={
            slot.date.isoformat()} &doctor={
            urllib.parse.quote_plus(slot.doctor_name)} "
        return redirect(redirect_url)

    patient_name = slot.patient_name
    slot.is_booked = False
    slot.patient_name = None
    slot.patient_phone = None
    slot.booked_by = None
    slot.receptionist_name = None
    slot.booked_at = None
    slot.booked_by_user = None
    slot.save()
    messages.info(
        request,
        f"Booking for {patient_name or 'patient'} at {slot.start_time.strftime('%I:%M %p')} with {slot.doctor_name} has been cancelled."
    )
    redirect_url = f"/?date={
        slot.date.isoformat()} &doctor={
        urllib.parse.quote_plus(slot.doctor_name)} "
    return redirect(redirect_url)


def seed_slots_view(request):
    """Manual trigger to generate 15-minute slots for requested date and doctor."""
    date_str = request.GET.get('date')
    if date_str:
        try:
            target_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            target_date = timezone.localdate()
    else:
        target_date = timezone.localdate()

    doctor_name = request.GET.get('doctor', '').strip() or DEFAULT_DOCTORS[0]

    ensure_doctor_slots_exist(target_date, doctor_name)
    messages.success(
        request,
        f"15-minute full-day schedule refreshed for {doctor_name} on {target_date.strftime('%A, %B %d, %Y')}."
    )
    redirect_url = f"/?date={
        target_date.isoformat()} &doctor={
        urllib.parse.quote_plus(doctor_name)} "
    return redirect(redirect_url)


def _build_redirect_response(request):
    """Helper to redirect back to current date, doctor, and period after form POSTs."""
    date_str = request.POST.get('current_date') or request.GET.get('date', '')
    doctor_str = request.POST.get(
        'selected_doctor') or request.GET.get('doctor', '')
    period_str = request.POST.get('period') or request.GET.get('period', '')
    query_params = {}
    if date_str:
        query_params['date'] = date_str
    if doctor_str:
        query_params['doctor'] = doctor_str
    if period_str and period_str != 'all':
        query_params['period'] = period_str

    redirect_url = '/'
    if query_params:
        redirect_url += '?' + urllib.parse.urlencode(query_params)
    return redirect(redirect_url)


@require_POST
def login_view(request):
    """
    Authenticates staff or administrator using telephone / mobile number as username and password.
    """
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '').strip()

    if not username or not password:
        messages.error(
            request,
            "Please enter both mobile number / username and password.")
    else:
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                display_name = user.first_name or user.username
                role_label = "Administrator" if (
                    user.is_staff or user.is_superuser) else "Staff Member"
                messages.success(
                    request, f"Welcome back, {display_name}! Signed in as {role_label}.")
            else:
                messages.error(
                    request,
                    "This account is currently deactivated. Please contact the clinic administrator.")
        else:
            messages.error(
                request,
                "Invalid mobile number or password. Please try again.")

    return _build_redirect_response(request)


@require_POST
def logout_view(request):
    """
    Signs out the current staff or administrator account.
    """
    logout(request)
    messages.info(request, "You have been safely signed out.")
    return _build_redirect_response(request)


@require_POST
def toggle_team_member_status(request, member_id):
    """
    Toggles the is_active status of a doctor or receptionist.
    Restricted strictly to clinic administrators.
    """
    if not (
            request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)):
        messages.error(
            request,
            "Access denied. Only clinic administrators can manage team member status.")
        return _build_redirect_response(request)

    member = get_object_or_404(TeamMember, pk=member_id)
    member.is_active = not member.is_active
    member.save()

    if member.user:
        member.user.is_active = member.is_active
        member.user.save()

    status_str = "reactivated on" if member.is_active else "deactivated from"
    role_str = member.get_role_display()
    messages.success(
        request,
        f"{role_str} '{member.name}' has been {status_str} the active roster. All historical booking records remain completely preserved."
    )

    return _build_redirect_response(request)


@require_POST
def add_team_member(request):
    """
    Adds a new doctor or receptionist to the clinic roster with mobile number as username and admin-assigned password.
    Restricted strictly to administrators.
    """
    if not (
            request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)):
        messages.error(
            request,
            "Access denied. Only clinic administrators can add team members.")
        return _build_redirect_response(request)

    name = request.POST.get('name', '').strip()
    role = request.POST.get('role', '').strip().lower()
    phone_number = request.POST.get('phone_number', '').strip()
    password = request.POST.get('password', '').strip()

    if not name:
        messages.error(request, "Staff member name cannot be empty.")
    elif not phone_number:
        messages.error(
            request, "Telephone / Mobile number (username) is required.")
    elif not password:
        messages.error(request, "Initial password is required.")
    elif len(password) < 4:
        messages.error(request, "Password must be at least 4 characters long.")
    elif role not in ('doctor', 'receptionist'):
        messages.error(
            request, "Invalid role selected. Must be Doctor or Receptionist.")
    elif User.objects.filter(username=phone_number).exists():
        messages.error(
            request, f"An account with mobile number '{phone_number}' already exists.")
    elif TeamMember.objects.filter(phone_number=phone_number).exists():
        messages.error(
            request, f"A team member with mobile number '{phone_number}' already exists.")
    else:
        user = User.objects.create_user(
            username=phone_number,
            password=password,
            first_name=name,
            is_staff=False
        )
        member = TeamMember.objects.create(
            name=name,
            role=role,
            phone_number=phone_number,
            user=user,
            is_active=True
        )
        messages.success(
            request,
            f"Successfully onboarded {member.get_role_display()} '{member.name}' with mobile username '{phone_number}'!"
        )

    return _build_redirect_response(request)


@require_POST
def reset_team_member_password(request, member_id):
    """
    Allows clinic administrators to edit / reset the password for a team member.
    """
    if not (
            request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)):
        messages.error(
            request,
            "Access denied. Only clinic administrators can reset staff passwords.")
        return _build_redirect_response(request)

    member = get_object_or_404(TeamMember, pk=member_id)
    new_password = request.POST.get('new_password', '').strip()

    if not new_password:
        messages.error(request, "New password cannot be empty.")
    elif len(new_password) < 4:
        messages.error(request, "Password must be at least 4 characters long.")
    else:
        user = member.user
        if not user:
            # If no user account was linked yet, create one with their phone_number or name
            username = member.phone_number or member.name.lower().replace(" ", "")
            user = User.objects.filter(username=username).first()
            if not user:
                user = User.objects.create_user(
                    username=username,
                    password=new_password,
                    first_name=member.name
                )
            else:
                user.set_password(new_password)
                user.save()
            member.user = user
            member.save()
        else:
            user.set_password(new_password)
            user.save()

        mobile_display = f" (Mobile: {
            member.phone_number}) "if member.phone_number else ""
        messages.success(
            request,
            f"Password for {member.get_role_display()} '{member.name}'{mobile_display} has been updated successfully."
        )

    return _build_redirect_response(request)
