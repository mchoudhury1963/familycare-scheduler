from django.db import models
from django.contrib.auth.models import User


class TimeSlot(models.Model):
    date = models.DateField()
    start_time = models.TimeField()
    doctor_name = models.CharField(max_length=150, default="Dr. Sarah Jenkins")
    is_booked = models.BooleanField(default=False)
    patient_name = models.CharField(max_length=150, blank=True, null=True)
    patient_phone = models.CharField(max_length=20, blank=True, null=True)
    booked_by = models.CharField(max_length=150, blank=True, null=True)
    receptionist_name = models.CharField(max_length=100, blank=True, null=True)
    booked_at = models.DateTimeField(blank=True, null=True)
    booked_by_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='booked_slots')

    class Meta:
        ordering = ['date', 'start_time', 'doctor_name']
        verbose_name = 'Time Slot'
        verbose_name_plural = 'Time Slots'
        unique_together = ('date', 'start_time', 'doctor_name')

    def __str__(self):
        time_str = self.start_time.strftime(
            '%I:%M %p') if self.start_time else ''
        status = f"Booked - {self.patient_name}" if self.is_booked else "Available"
        return f"{self.doctor_name} | {self.date} {time_str} ({status})"


class TeamMember(models.Model):
    ROLE_CHOICES = [
        ('doctor', 'Doctor'),
        ('receptionist', 'Receptionist'),
    ]
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='team_profile')
    name = models.CharField(max_length=150, unique=True)
    phone_number = models.CharField(
        max_length=30, blank=True, null=True, unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['role', 'name']
        verbose_name = 'Team Member'
        verbose_name_plural = 'Team Members'

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.name} ({self.get_role_display()}) - {status}"
