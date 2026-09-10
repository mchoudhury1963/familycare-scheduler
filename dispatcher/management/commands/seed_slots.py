import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from dispatcher.models import TimeSlot
from dispatcher.views import DEFAULT_DOCTORS, generate_full_day_15min_times


class Command(BaseCommand):
    help = 'Seeds full-day 15-minute schedule slots (8:00 AM - Midnight) for doctors.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Target date in YYYY-MM-DD format (defaults to today)',
        )
        parser.add_argument(
            '--doctor',
            type=str,
            help='Specific doctor name (defaults to all standard doctors if omitted)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing slots for the target date and doctor(s) before seeding',
        )

    def handle(self, *args, **options):
        date_str = options.get('date')
        if date_str:
            try:
                target_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                self.stderr.write(self.style.ERROR(
                    f"Invalid date format: {date_str}. Expected YYYY-MM-DD."))
                return
        else:
            target_date = timezone.localdate()

        doctor_arg = options.get('doctor')
        target_doctors = [doctor_arg] if doctor_arg else DEFAULT_DOCTORS

        if options.get('clear'):
            deleted_count, _ = TimeSlot.objects.filter(
                date=target_date,
                doctor_name__in=target_doctors
            ).delete()
            self.stdout.write(self.style.WARNING(
                f"Cleared {deleted_count} existing slot(s) for {target_date}."))

        times = generate_full_day_15min_times()
        total_created = 0

        for doc in target_doctors:
            doc_created = 0
            for slot_time in times:
                _, created = TimeSlot.objects.get_or_create(
                    date=target_date,
                    start_time=slot_time,
                    doctor_name=doc,
                )
                if created:
                    doc_created += 1
            total_created += doc_created
            self.stdout.write(
                f"  - {doc}: {len(times)} slots ready ({doc_created} newly created)."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully seeded 15-minute slots for {len(target_doctors)} doctor(s) on {target_date.strftime('%A, %B %d, %Y')} "
                f"({total_created} total new slots created)."
            )
        )
