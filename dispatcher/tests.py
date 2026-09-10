import datetime
import urllib.parse
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User
from .models import TimeSlot, TeamMember
from .views import DEFAULT_DOCTORS, DEFAULT_ADMIN_MOBILE, DEFAULT_ADMIN_PASS


class MultiDoctorSchedulerTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.today = timezone.localdate()
        self.doc1 = "Dr. Sarah Jenkins"
        self.doc2 = "Dr. Marcus Chen"

        # Pre-seed a booked slot for Dr. Sarah Jenkins
        self.booked_slot = TimeSlot.objects.create(
            date=self.today,
            start_time=datetime.time(8, 15, 0),
            doctor_name=self.doc1,
            is_booked=True,
            patient_name="Existing Patient",
            patient_phone="(555) 123-4567",
            booked_by="Receptionist Mary",
            receptionist_name="Receptionist Emily"
        )

        # Pre-seed an open slot for Dr. Sarah Jenkins
        self.open_slot = TimeSlot.objects.create(
            date=self.today,
            start_time=datetime.time(8, 30, 0),
            doctor_name=self.doc1,
            is_booked=False
        )

    def test_timeslot_model_properties(self):
        """Test TimeSlot model attributes, doctor_name, booked_by, receptionist_name, and string formatting."""
        slot = self.open_slot
        self.assertEqual(slot.date, self.today)
        self.assertEqual(slot.start_time, datetime.time(8, 30, 0))
        self.assertEqual(slot.doctor_name, self.doc1)
        self.assertFalse(slot.is_booked)
        self.assertIsNone(slot.patient_name)
        self.assertIsNone(slot.patient_phone)
        self.assertIsNone(slot.booked_by)
        self.assertIsNone(slot.receptionist_name)
        self.assertIn("08:30 AM", str(slot))
        self.assertIn("Available", str(slot))
        self.assertIn(self.doc1, str(slot))

        booked = self.booked_slot
        self.assertTrue(booked.is_booked)
        self.assertEqual(booked.patient_name, "Existing Patient")
        self.assertEqual(booked.patient_phone, "(555) 123-4567")
        self.assertEqual(booked.booked_by, "Receptionist Mary")
        self.assertEqual(booked.receptionist_name, "Receptionist Emily")
        self.assertIn("Existing Patient", str(booked))

    def test_daily_calendar_auto_seeds_15min_full_day_slots(self):
        """Verify calendar auto-seeds 15-minute slots across the full day (8 AM - Midnight)."""
        url = reverse('dispatcher:daily_calendar')
        response = self.client.get(url, {'doctor': self.doc1})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dispatcher/daily_calendar.html')

        # Check total slots for doc1 is 64 (from 08:00 to 23:45 every 15 mins)
        doc1_slots = TimeSlot.objects.filter(
            date=self.today, doctor_name=self.doc1)
        self.assertEqual(doc1_slots.count(), 64)

        # Check HTML contains 15 mins indicators, doctor name, and staff info
        self.assertContains(response, "15 mins")
        self.assertContains(response, self.doc1)
        self.assertContains(response, "slot-card-available")
        self.assertContains(response, "slot-card-booked")
        self.assertContains(response, "Existing Patient")
        self.assertContains(response, "(555) 123-4567")
        self.assertContains(response, "Receptionist Mary")
        self.assertContains(response, "Handled by:")
        self.assertContains(response, "Receptionist Emily")
        self.assertIn('staff_list', response.context)

    def test_multi_doctor_schedule_isolation(self):
        """Verify switching doctor displays that doctor's distinct schedule."""
        # Request schedule for doc2
        url = reverse('dispatcher:daily_calendar')
        response = self.client.get(url, {'doctor': self.doc2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_doctor'], self.doc2)

        # doc2 should have their own 64 slots, and should not show doc1's booked patient
        doc2_slots = TimeSlot.objects.filter(
            date=self.today, doctor_name=self.doc2)
        self.assertEqual(doc2_slots.count(), 64)
        self.assertNotContains(response, "Existing Patient")

    def test_period_filter_morning_afternoon_evening(self):
        """Verify filtering by morning, afternoon, and evening blocks."""
        url = reverse('dispatcher:daily_calendar')

        # Morning filter: < 12:00 (8:00 to 11:45 = 16 slots)
        r_morning = self.client.get(
            url, {'doctor': self.doc1, 'period': 'morning'})
        morning_slots = list(r_morning.context['slots'])
        self.assertEqual(len(morning_slots), 16)
        self.assertTrue(all(s.start_time < datetime.time(12, 0)
                        for s in morning_slots))

        # Afternoon filter: 12:00 to 16:45 = 20 slots
        r_afternoon = self.client.get(
            url, {'doctor': self.doc1, 'period': 'afternoon'})
        afternoon_slots = list(r_afternoon.context['slots'])
        self.assertEqual(len(afternoon_slots), 20)
        self.assertTrue(all(datetime.time(12, 0) <= s.start_time <
                        datetime.time(17, 0) for s in afternoon_slots))

        # Evening filter: 17:00 to 23:45 = 28 slots
        r_evening = self.client.get(
            url, {'doctor': self.doc1, 'period': 'evening'})
        evening_slots = list(r_evening.context['slots'])
        self.assertEqual(len(evening_slots), 28)
        self.assertTrue(all(s.start_time >= datetime.time(17, 0)
                        for s in evening_slots))

    def test_ping_endpoint_returns_ok(self):
        """Verify keep-alive ping endpoint returns 200 OK with plain text."""
        url = reverse('dispatcher:ping')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode('utf-8'), "OK")
        self.assertEqual(response['Content-Type'], "text/plain")

    def test_unauthenticated_cannot_book_or_cancel_slot(self):
        """Unauthenticated visitors cannot book or release slots (redirected to LOGIN_URL)."""
        self.client.logout()

        # Try booking unauthenticated
        book_url = reverse('dispatcher:book_slot_post')
        book_res = self.client.post(book_url, {
            'slot_id': self.open_slot.id,
            'patient_name': 'Unauthorized Guest',
            'patient_phone': '01700000000',
        })
        self.assertEqual(book_res.status_code, 302)
        self.assertIn('/?', book_res.url)
        self.open_slot.refresh_from_db()
        self.assertFalse(self.open_slot.is_booked)

        # Try cancelling unauthenticated
        cancel_url = reverse('dispatcher:cancel_slot', kwargs={
                             'slot_id': self.booked_slot.id})
        cancel_res = self.client.post(cancel_url)
        self.assertEqual(cancel_res.status_code, 302)
        self.assertIn('/?', cancel_res.url)
        self.booked_slot.refresh_from_db()
        self.assertTrue(self.booked_slot.is_booked)

    def test_book_15min_slot_with_phone_and_redirect(self):
        """Test booking a 15-minute slot with phone, booked_by, and receptionist_name as authenticated staff."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        self.client.login(username=DEFAULT_ADMIN_MOBILE,
                          password=DEFAULT_ADMIN_PASS)

        url = reverse('dispatcher:book_slot_post')
        post_data = {
            'slot_id': self.open_slot.id,
            'patient_name': 'Jonathan Crane',
            'patient_phone': '(555) 987-6543',
            'booked_by': 'Bruce Wayne (Guardian)',
            'receptionist_name': 'Receptionist Alex',
        }
        response = self.client.post(url, post_data)

        # Redirect should preserve date and doctor
        expected_redirect = f"/?date={
            self.today.isoformat()} &doctor={
            urllib.parse.quote_plus(self.doc1)} "
        self.assertRedirects(response, expected_redirect)

        self.open_slot.refresh_from_db()
        self.assertTrue(self.open_slot.is_booked)
        self.assertEqual(self.open_slot.patient_name, 'Jonathan Crane')
        self.assertEqual(self.open_slot.patient_phone, '(555) 987-6543')
        self.assertEqual(self.open_slot.booked_by, 'Bruce Wayne (Guardian)')
        self.assertEqual(self.open_slot.receptionist_name, 'Receptionist Alex')

    def test_book_slot_missing_required_fields(self):
        """Booking requires both patient name and phone number for call tracking."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        self.client.login(username=DEFAULT_ADMIN_MOBILE,
                          password=DEFAULT_ADMIN_PASS)

        url = reverse('dispatcher:book_slot_post')

        # Test missing name
        response = self.client.post(url, {
            'slot_id': self.open_slot.id,
            'patient_name': '  ',
            'patient_phone': '(555) 111-2222',
        })
        self.assertEqual(response.status_code, 302)
        self.open_slot.refresh_from_db()
        self.assertFalse(self.open_slot.is_booked)

        # Test missing phone
        response2 = self.client.post(url, {
            'slot_id': self.open_slot.id,
            'patient_name': 'Bruce Wayne',
            'patient_phone': '  ',
        })
        self.assertEqual(response2.status_code, 302)
        self.open_slot.refresh_from_db()
        self.assertFalse(self.open_slot.is_booked)

    def test_cancel_slot_preserves_doctor_and_date(self):
        """Test releasing a slot clears patient info, booked_by, receptionist_name, and redirects."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        self.client.login(username=DEFAULT_ADMIN_MOBILE,
                          password=DEFAULT_ADMIN_PASS)

        url = reverse('dispatcher:cancel_slot', kwargs={
                      'slot_id': self.booked_slot.id})
        response = self.client.post(url)

        expected_redirect = f"/?date={
            self.today.isoformat()} &doctor={
            urllib.parse.quote_plus(self.doc1)} "
        self.assertRedirects(response, expected_redirect)

        self.booked_slot.refresh_from_db()
        self.assertFalse(self.booked_slot.is_booked)
        self.assertIsNone(self.booked_slot.patient_name)
        self.assertIsNone(self.booked_slot.patient_phone)
        self.assertIsNone(self.booked_slot.booked_by)
        self.assertIsNone(self.booked_slot.receptionist_name)
        self.assertIsNone(self.booked_slot.booked_at)
        self.assertIsNone(self.booked_slot.booked_by_user)

    def test_dynamic_doctor_input_generates_schedule(self):
        """Entering a custom/new doctor name generates their 64-slot 8 AM to Midnight schedule."""
        new_doc = "Dr. Gregory House"
        url = reverse('dispatcher:daily_calendar')
        response = self.client.get(url, {'doctor': new_doc})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_doctor'], new_doc)
        self.assertEqual(TimeSlot.objects.filter(
            doctor_name=new_doc, date=self.today).count(), 64)
        self.assertContains(response, new_doc)

    def test_team_member_model_and_seeding(self):
        """Test TeamMember model attributes, string formatting, and default seeding."""
        url = reverse('dispatcher:daily_calendar')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # TeamMember should contain default doctors and staff
        self.assertTrue(TeamMember.objects.filter(
            name=self.doc1, role='doctor').exists())
        member = TeamMember.objects.get(name=self.doc1)
        self.assertTrue(member.is_active)
        self.assertIn("Active", str(member))
        self.assertIn(self.doc1, str(member))

    def test_deactivate_doctor_removes_from_active_list_but_preserves_slots(
            self):
        """
        Deactivating a doctor removes them from active dropdowns/pills,
        but safely preserves historical patient booking records for auditing.
        """
        # Ensure team exists
        self.client.get(reverse('dispatcher:daily_calendar'))
        doc_member = TeamMember.objects.get(name=self.doc1)
        doc_member.is_active = False
        doc_member.save()

        # Load calendar for active roster
        response = self.client.get(reverse('dispatcher:daily_calendar'))
        self.assertNotIn(self.doc1, response.context['active_doctors'])

        # Directly visit deactivated doctor's schedule for auditing
        audit_response = self.client.get(
            reverse('dispatcher:daily_calendar'),
            {'doctor': self.doc1})
        self.assertFalse(audit_response.context['is_current_doctor_active'])
        self.assertContains(audit_response, "Historical Schedule & Audit Mode")
        self.assertContains(audit_response, "Existing Patient")

        # Confirm booking still exists intact in the database
        self.booked_slot.refresh_from_db()
        self.assertTrue(self.booked_slot.is_booked)
        self.assertEqual(self.booked_slot.patient_name, "Existing Patient")

    def test_deactivate_receptionist_removes_from_modal_dropdown(self):
        """Deactivating a receptionist removes them from the booking modal options."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        staff_member = TeamMember.objects.get(name="Receptionist Alex")
        staff_member.is_active = False
        staff_member.save()

        response = self.client.get(reverse('dispatcher:daily_calendar'))
        self.assertNotIn("Receptionist Alex", response.context['staff_list'])

    def test_toggle_team_member_status_post(self):
        """POST to toggle_team_member changes is_active state when performed by admin."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        # Authenticate as admin
        self.client.login(username=DEFAULT_ADMIN_MOBILE,
                          password=DEFAULT_ADMIN_PASS)

        member = TeamMember.objects.get(name=self.doc2)
        self.assertTrue(member.is_active)

        toggle_url = reverse('dispatcher:toggle_team_member',
                             kwargs={'member_id': member.id})
        post_data = {
            'current_date': self.today.isoformat(),
            'selected_doctor': self.doc1,
            'period': 'all',
        }
        res = self.client.post(toggle_url, post_data)
        self.assertEqual(res.status_code, 302)

        member.refresh_from_db()
        self.assertFalse(member.is_active)

        # Toggle back to active
        res2 = self.client.post(toggle_url, post_data)
        self.assertEqual(res2.status_code, 302)
        member.refresh_from_db()
        self.assertTrue(member.is_active)

    def test_add_new_team_member_post(self):
        """POST to add_team_member successfully adds a new doctor or receptionist with mobile and password."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        # Authenticate as admin
        self.client.login(username=DEFAULT_ADMIN_MOBILE,
                          password=DEFAULT_ADMIN_PASS)

        add_url = reverse('dispatcher:add_team_member')
        post_data = {
            'name': 'Dr. Meredith Grey',
            'role': 'doctor',
            'phone_number': '01719999999',
            'password': 'GreyPassword123!',
            'current_date': self.today.isoformat(),
            'selected_doctor': self.doc1,
            'period': 'all',
        }
        res = self.client.post(add_url, post_data)
        self.assertEqual(res.status_code, 302)

        new_doc = TeamMember.objects.filter(name='Dr. Meredith Grey').first()
        self.assertIsNotNone(new_doc)
        self.assertEqual(new_doc.role, 'doctor')
        self.assertEqual(new_doc.phone_number, '01719999999')
        self.assertTrue(new_doc.is_active)
        self.assertIsNotNone(new_doc.user)
        self.assertEqual(new_doc.user.username, '01719999999')
        self.assertTrue(new_doc.user.check_password('GreyPassword123!'))

    def test_login_with_mobile_number_and_logout(self):
        """Test sign-in with telephone number as username and subsequent sign-out."""
        self.client.get(reverse('dispatcher:daily_calendar'))

        login_url = reverse('dispatcher:login')
        post_data = {
            'username': DEFAULT_ADMIN_MOBILE,
            'password': DEFAULT_ADMIN_PASS,
            'current_date': self.today.isoformat(),
            'selected_doctor': self.doc1,
            'period': 'all',
        }
        res = self.client.post(login_url, post_data)
        self.assertEqual(res.status_code, 302)

        # Confirm calendar page shows admin badge with real name and Manage Team button
        cal_res = self.client.get(reverse('dispatcher:daily_calendar'))
        self.assertContains(cal_res, "Admin: Clinic Admin")
        self.assertContains(cal_res, "Manage Team")
        self.assertContains(cal_res, 'id="manageTeamModal"')

        # Now logout
        logout_url = reverse('dispatcher:logout')
        logout_res = self.client.post(logout_url, {
            'current_date': self.today.isoformat(),
            'selected_doctor': self.doc1,
            'period': 'all',
        })
        self.assertEqual(logout_res.status_code, 302)

        # Unauthenticated calendar view
        anon_res = self.client.get(reverse('dispatcher:daily_calendar'))
        self.assertContains(anon_res, "Sign In")
        self.assertContains(anon_res, "Sign In to Book")
        self.assertNotContains(anon_res, "Admin: Clinic Admin")
        self.assertNotContains(anon_res, 'id="manageTeamModal"')
        self.assertNotContains(anon_res, 'id="updateStaffDetailsModal"')

    def test_login_invalid_credentials(self):
        """Test sign-in failure with incorrect mobile or password."""
        self.client.get(reverse('dispatcher:daily_calendar'))

        login_url = reverse('dispatcher:login')
        res = self.client.post(login_url, {
            'username': DEFAULT_ADMIN_MOBILE,
            'password': 'WrongPasswordXYZ',
        })
        self.assertEqual(res.status_code, 302)

        # Should remain unauthenticated
        cal_res = self.client.get(reverse('dispatcher:daily_calendar'))
        self.assertContains(cal_res, "Sign In")

    def test_admin_onboard_staff_and_staff_login(self):
        """Admin onboards a new receptionist with mobile & password, staff signs in successfully."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        self.client.login(username=DEFAULT_ADMIN_MOBILE,
                          password=DEFAULT_ADMIN_PASS)

        add_url = reverse('dispatcher:add_team_member')
        staff_mobile = "01788776655"
        staff_pass = "StaffSecret2026!"

        res = self.client.post(add_url, {
            'name': 'Receptionist Sam',
            'role': 'receptionist',
            'phone_number': staff_mobile,
            'password': staff_pass,
        })
        self.assertEqual(res.status_code, 302)

        member = TeamMember.objects.filter(phone_number=staff_mobile).first()
        self.assertIsNotNone(member)
        self.assertEqual(member.name, 'Receptionist Sam')

        # Admin logs out
        self.client.logout()

        # Staff logs in with mobile number
        login_res = self.client.post(reverse('dispatcher:login'), {
            'username': staff_mobile,
            'password': staff_pass,
        })
        self.assertEqual(login_res.status_code, 302)

        # Verify staff view: has staff badge with real name, but Manage Team is HIDDEN
        staff_cal = self.client.get(reverse('dispatcher:daily_calendar'))
        self.assertContains(staff_cal, "Staff: Receptionist Sam")
        self.assertNotContains(staff_cal, "Manage Team")
        self.assertNotContains(staff_cal, 'id="manageTeamModal"')
        self.assertNotContains(staff_cal, 'id="updateStaffDetailsModal"')

    def test_admin_reset_staff_password(self):
        """Admin can reset a staff member's password from the roster."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        self.client.login(username=DEFAULT_ADMIN_MOBILE,
                          password=DEFAULT_ADMIN_PASS)

        # Get Receptionist Alex (seeded with mobile 01712000002)
        alex = TeamMember.objects.get(name="Receptionist Alex")
        reset_url = reverse(
            'dispatcher:reset_team_member_password',
            kwargs={'member_id': alex.id})
        new_password = "AlexBrandNewPass2026!"

        res = self.client.post(reset_url, {
            'new_password': new_password,
            'current_date': self.today.isoformat(),
            'selected_doctor': self.doc1,
            'period': 'all',
        })
        self.assertEqual(res.status_code, 302)

        # Alex's user should have the updated password
        alex.refresh_from_db()
        self.assertTrue(alex.user.check_password(new_password))

        # Alex logs in with new password
        self.client.logout()
        alex_login = self.client.post(reverse('dispatcher:login'), {
            'username': alex.phone_number,
            'password': new_password,
        })
        self.assertEqual(alex_login.status_code, 302)

    def test_admin_update_team_member_details_name_and_phone_only(self):
        """Admin can update staff name and phone without changing password, preserving historical bookings."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        self.client.login(username=DEFAULT_ADMIN_MOBILE,
                          password=DEFAULT_ADMIN_PASS)

        alex = TeamMember.objects.get(name="Receptionist Alex")
        old_password = "StaffPass123!"

        # Create a booking previously handled by Alex
        booking = TimeSlot.objects.create(
            date=self.today,
            start_time=datetime.time(10, 0, 0),
            doctor_name=self.doc1,
            is_booked=True,
            patient_name="Historic Patient",
            patient_phone="01799988877",
            booked_by="Self",
            receptionist_name="Receptionist Alex",
            booked_by_user=alex.user,
            booked_at=timezone.now()
        )

        update_url = reverse('dispatcher:update_team_member',
                             kwargs={'member_id': alex.id})
        new_name = "Receptionist Alexander"
        new_phone = "01712999999"

        res = self.client.post(update_url, {
            'name': new_name,
            'phone_number': new_phone,
            'new_password': '',  # Leave blank to keep existing password
        })
        self.assertEqual(res.status_code, 302)

        alex.refresh_from_db()
        self.assertEqual(alex.name, new_name)
        self.assertEqual(alex.phone_number, new_phone)
        self.assertEqual(alex.user.first_name, new_name)
        self.assertEqual(alex.user.username, new_phone)
        self.assertTrue(alex.user.check_password(old_password))

        # Historic booking remains intact
        booking.refresh_from_db()
        self.assertEqual(booking.patient_name, "Historic Patient")
        self.assertEqual(booking.receptionist_name, "Receptionist Alex")
        self.assertEqual(booking.booked_by_user_id, alex.user.id)

        # Alex can sign in with new phone username and original password
        self.client.logout()
        alex_login = self.client.post(reverse('dispatcher:login'), {
            'username': new_phone,
            'password': old_password,
        })
        self.assertEqual(alex_login.status_code, 302)

    def test_admin_update_team_member_details_with_password(self):
        """Admin can update staff name, phone, and assign a new password simultaneously."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        self.client.login(username=DEFAULT_ADMIN_MOBILE,
                          password=DEFAULT_ADMIN_PASS)

        alex = TeamMember.objects.get(name="Receptionist Alex")
        update_url = reverse('dispatcher:update_team_member',
                             kwargs={'member_id': alex.id})

        res = self.client.post(update_url, {
            'name': 'Receptionist Alexander Graham',
            'phone_number': '01712888888',
            'new_password': 'NewSuperSecurePass2026!',
        })
        self.assertEqual(res.status_code, 302)

        alex.refresh_from_db()
        self.assertEqual(alex.name, 'Receptionist Alexander Graham')
        self.assertEqual(alex.phone_number, '01712888888')
        self.assertTrue(alex.user.check_password('NewSuperSecurePass2026!'))

        # Login with new credentials
        self.client.logout()
        alex_login = self.client.post(reverse('dispatcher:login'), {
            'username': '01712888888',
            'password': 'NewSuperSecurePass2026!',
        })
        self.assertEqual(alex_login.status_code, 302)

    def test_update_team_member_duplicate_phone_validation(self):
        """Updating to a phone number already used by another member is prevented."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        self.client.login(username=DEFAULT_ADMIN_MOBILE,
                          password=DEFAULT_ADMIN_PASS)

        emily = TeamMember.objects.get(
            name="Receptionist Emily")  # phone 01712000001
        alex = TeamMember.objects.get(name="Receptionist Alex")

        update_url = reverse('dispatcher:update_team_member',
                             kwargs={'member_id': alex.id})
        res = self.client.post(update_url, {
            'name': 'Receptionist Alex',
            'phone_number': emily.phone_number,
        })
        self.assertEqual(res.status_code, 302)
        alex.refresh_from_db()
        self.assertNotEqual(alex.phone_number, emily.phone_number)

    def test_access_control_manage_team_forbidden_for_staff_and_guests(self):
        """Guests and regular staff cannot access add_team_member, reset_password, update_team_member, or toggle_member."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        target_member = TeamMember.objects.get(name=self.doc2)

        toggle_url = reverse(
            'dispatcher:toggle_team_member',
            kwargs={'member_id': target_member.id})
        reset_url = reverse(
            'dispatcher:reset_team_member_password',
            kwargs={'member_id': target_member.id})
        update_url = reverse(
            'dispatcher:update_team_member',
            kwargs={'member_id': target_member.id})
        add_url = reverse('dispatcher:add_team_member')

        # 1. Anonymous guest
        self.client.logout()
        r1 = self.client.post(toggle_url, {})
        self.assertEqual(r1.status_code, 302)
        target_member.refresh_from_db()
        self.assertTrue(target_member.is_active)  # Unchanged!

        r2 = self.client.post(
            reset_url, {'new_password': 'HackedPassword123!'})
        self.assertEqual(r2.status_code, 302)
        target_member.refresh_from_db()
        self.assertFalse(target_member.user.check_password(
            'HackedPassword123!'))  # Unchanged!

        r2b = self.client.post(
            update_url, {'name': 'Hacked Name', 'phone_number': '01799990000'})
        self.assertEqual(r2b.status_code, 302)
        target_member.refresh_from_db()
        self.assertNotEqual(target_member.name, 'Hacked Name')

        r3 = self.client.post(
            add_url,
            {'name': 'Unauthorized User', 'role': 'doctor',
             'phone_number': '01700009999', 'password': 'pass'})
        self.assertEqual(r3.status_code, 302)
        self.assertFalse(TeamMember.objects.filter(
            name='Unauthorized User').exists())

        # 2. Regular staff member (non-admin)
        self.client.login(username="01712000001", password="StaffPass123!")
        r4 = self.client.post(toggle_url, {})
        self.assertEqual(r4.status_code, 302)
        target_member.refresh_from_db()
        self.assertTrue(target_member.is_active)  # Still active!

        r5 = self.client.post(
            reset_url, {'new_password': 'HackedPassword123!'})
        self.assertEqual(r5.status_code, 302)
        target_member.refresh_from_db()
        self.assertFalse(target_member.user.check_password(
            'HackedPassword123!'))

        r5b = self.client.post(
            update_url,
            {'name': 'Staff Modified Doc', 'phone_number': '01799990000'})
        self.assertEqual(r5b.status_code, 302)
        target_member.refresh_from_db()
        self.assertNotEqual(target_member.name, 'Staff Modified Doc')

        r6 = self.client.post(
            add_url,
            {'name': 'Unauthorized Staff Add', 'role': 'receptionist',
             'phone_number': '01700008888', 'password': 'pass'})
        self.assertEqual(r6.status_code, 302)
        self.assertFalse(TeamMember.objects.filter(
            name='Unauthorized Staff Add').exists())

    def test_booking_records_creation_timestamp_and_user(self):
        """Booking a slot sets booked_at to current timestamp and booked_by_user to authenticated user."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        self.client.login(username="01712000001", password="StaffPass123!")

        url = reverse('dispatcher:book_slot_post')
        post_data = {
            'slot_id': self.open_slot.id,
            'patient_name': 'Diana Prince',
            'patient_phone': '01755512345',
            'booked_by': 'Diana Prince',
            'receptionist_name': 'Receptionist Emily',
        }
        res = self.client.post(url, post_data)
        self.assertEqual(res.status_code, 302)

        self.open_slot.refresh_from_db()
        self.assertTrue(self.open_slot.is_booked)
        self.assertIsNotNone(self.open_slot.booked_at)
        self.assertIsNotNone(self.open_slot.booked_by_user)
        self.assertEqual(self.open_slot.booked_by_user.username, "01712000001")

    def test_booked_card_displays_creation_timestamp(self):
        """Booked slot cards cleanly display their formatted database creation timestamp."""
        self.client.get(reverse('dispatcher:daily_calendar'))

        # Simulate advance booking saved two days prior
        created_dt = timezone.datetime(
            2026, 9, 7, 9, 30, tzinfo=timezone.get_current_timezone())
        self.booked_slot.booked_at = created_dt
        self.booked_slot.save()

        res = self.client.get(
            reverse('dispatcher:daily_calendar'),
            {'doctor': self.doc1})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Booked: 09/07/2026, 09:30 AM")

    def test_release_slot_permission_allowed_for_creator(self):
        """Staff member who created the booking can view and click Release Slot."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        emily_user = User.objects.get(username="01712000001")
        self.booked_slot.booked_by_user = emily_user
        self.booked_slot.booked_at = timezone.now()
        self.booked_slot.save()

        # Login as Emily (creator)
        self.client.login(username="01712000001", password="StaffPass123!")
        cal_res = self.client.get(
            reverse('dispatcher:daily_calendar'),
            {'doctor': self.doc1})
        self.assertContains(cal_res, "Release Slot")
        self.assertNotContains(cal_res, "Slot Locked")

        # Emily cancels the slot
        cancel_url = reverse('dispatcher:cancel_slot', kwargs={
                             'slot_id': self.booked_slot.id})
        res = self.client.post(cancel_url)
        self.assertEqual(res.status_code, 302)

        self.booked_slot.refresh_from_db()
        self.assertFalse(self.booked_slot.is_booked)
        self.assertIsNone(self.booked_slot.booked_at)
        self.assertIsNone(self.booked_slot.booked_by_user)

    def test_release_slot_permission_allowed_for_admin(self):
        """Clinic administrator can release any slot, regardless of who booked it."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        emily_user = User.objects.get(username="01712000001")
        self.booked_slot.booked_by_user = emily_user
        self.booked_slot.booked_at = timezone.now()
        self.booked_slot.save()

        # Login as Admin
        self.client.login(username=DEFAULT_ADMIN_MOBILE,
                          password=DEFAULT_ADMIN_PASS)
        cal_res = self.client.get(
            reverse('dispatcher:daily_calendar'),
            {'doctor': self.doc1})
        self.assertContains(cal_res, "Release Slot")

        # Admin cancels the slot
        cancel_url = reverse('dispatcher:cancel_slot', kwargs={
                             'slot_id': self.booked_slot.id})
        res = self.client.post(cancel_url)
        self.assertEqual(res.status_code, 302)

        self.booked_slot.refresh_from_db()
        self.assertFalse(self.booked_slot.is_booked)
        self.assertIsNone(self.booked_slot.booked_at)
        self.assertIsNone(self.booked_slot.booked_by_user)

    def test_release_slot_permission_denied_for_colleague_and_guest(self):
        """Colleague and guest can view all booking details, but Release Slot is locked."""
        self.client.get(reverse('dispatcher:daily_calendar'))
        emily_user = User.objects.get(username="01712000001")
        self.booked_slot.booked_by_user = emily_user
        self.booked_slot.booked_at = timezone.now()
        self.booked_slot.save()

        cancel_url = reverse('dispatcher:cancel_slot', kwargs={
                             'slot_id': self.booked_slot.id})

        # 1. Colleague Alex (01712000002)
        self.client.login(username="01712000002", password="StaffPass123!")
        alex_view = self.client.get(
            reverse('dispatcher:daily_calendar'),
            {'doctor': self.doc1})
        # Alex sees full details
        self.assertContains(alex_view, "Existing Patient")
        self.assertContains(alex_view, "(555) 123-4567")
        self.assertContains(alex_view, "Receptionist Mary")
        self.assertContains(alex_view, "Receptionist Emily")
        self.assertContains(alex_view, "Booked:")
        # But button is locked
        self.assertContains(alex_view, "Slot Locked")
        self.assertNotContains(alex_view, "Release Slot")

        # Attempt unauthorized POST
        alex_post = self.client.post(cancel_url)
        self.assertEqual(alex_post.status_code, 302)
        self.booked_slot.refresh_from_db()
        self.assertTrue(self.booked_slot.is_booked)  # Still booked!

        # 2. Anonymous guest
        self.client.logout()
        guest_view = self.client.get(
            reverse('dispatcher:daily_calendar'),
            {'doctor': self.doc1})
        self.assertContains(guest_view, "Slot Locked")
        self.assertNotContains(guest_view, "Release Slot")

        guest_post = self.client.post(cancel_url)
        self.assertEqual(guest_post.status_code, 302)
        self.booked_slot.refresh_from_db()
        self.assertTrue(self.booked_slot.is_booked)  # Still booked!

    def test_smart_receptionist_intake_locked_for_staff_and_selectable_for_admin(self):
        """Regular staff booking automatically locks receptionist_name to their name; admin can choose any."""
        self.client.get(reverse('dispatcher:daily_calendar'))

        # 1. Regular staff Emily (01712000001) books
        self.client.login(username="01712000001", password="StaffPass123!")

        # Staff view has read-only intake input
        staff_cal = self.client.get(reverse('dispatcher:daily_calendar'))
        self.assertContains(staff_cal, "Receptionist Emily")
        self.assertContains(
            staff_cal, "Automatically locked to your staff intake account.")

        # Even if someone sends a spoofed receptionist_name via POST, backend locks to Emily
        res = self.client.post(reverse('dispatcher:book_slot_post'), {
            'slot_id': self.open_slot.id,
            'patient_name': 'Clark Kent',
            'patient_phone': '01711122233',
            'booked_by': 'Clark Kent',
            'receptionist_name': 'Spoofed Person',
        })
        self.assertEqual(res.status_code, 302)
        self.open_slot.refresh_from_db()
        self.assertEqual(self.open_slot.receptionist_name,
                         "Receptionist Emily")
        self.assertEqual(self.open_slot.booked_by_user.username, "01712000001")

        # 2. Admin logs in: can choose any receptionist
        self.client.logout()
        self.client.login(username=DEFAULT_ADMIN_MOBILE,
                          password=DEFAULT_ADMIN_PASS)
        admin_cal = self.client.get(reverse('dispatcher:daily_calendar'))
        self.assertContains(admin_cal, 'id="receptionistSelect"')
        self.assertContains(
            admin_cal, "Administrator mode: Select any receptionist")
