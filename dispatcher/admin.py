from django.contrib import admin
from .models import TimeSlot, TeamMember


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = (
        'date', 'start_time', 'doctor_name', 'is_booked', 'patient_name',
        'patient_phone', 'booked_by', 'receptionist_name', 'booked_at',
        'booked_by_user')
    list_filter = ('date', 'doctor_name', 'is_booked',
                   'receptionist_name', 'booked_at')
    search_fields = ('doctor_name', 'patient_name',
                     'patient_phone', 'booked_by', 'receptionist_name',
                     'booked_by_user__username')

    ordering = ('date', 'start_time', 'doctor_name')


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone_number', 'role',
                    'is_active', 'user', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('name', 'phone_number')
    ordering = ('role', 'name')
