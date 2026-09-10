# FamilyCare Booking - Full-Day Multi-Doctor 15-Minute Scheduler

A standalone Django application tailored for clinic operations, multi-doctor scheduling, and 15-minute appointment dispatching across the entire day.

## Key Features
- **Multi-Doctor Scheduling**: Separate, isolated daily schedules for doctors (e.g., Dr. Sarah Jenkins, Dr. Marcus Chen, Dr. Priya Patel, Dr. Alexander Ross).
- **15-Minute Precision Grid**: Full-day coverage (8:00 AM to 8:00 PM) in 15-minute intervals (49 slots/doctor/day).
- **Control Bar**:
  - **Attending Physician Selector**: Dropdown to switch between doctors with automatic dynamic refresh.
  - **Date Picker**: Date picker with **Previous Day**, **Today**, and **Next Day** one-click quick controls.
  - **Time Block Filters**: Quick filter pills for All Day, Morning (8am-12pm), Afternoon (12pm-5pm), and Evening (5pm-8pm).
- **Color-Coded Card Grid**:
  - **Available Slots**: Vibrant emerald green border and 6px solid green left accent (`#10b981`), "Available" badge, touch-friendly "Book Patient" button.
  - **Booked Slots**: Clean, light cream wash with striking top-left Amber accent border (`#FFBF00`), dedicated Amber "Booked" badge, patient name, caller info, staff intake, and patient phone with a 1-click "Call" button (`tel:...`).
- **Centered Booking Modal**:
  - Automatically loads selected doctor and slot time.
  - Side-by-side inputs for **Patient Full Name** and **Patient Phone Number**.
- **Management Command & Auto-Seeding**:
  - Built-in auto-seeding ensures any selected doctor has full-day 15-minute slots immediately upon page load.
  - `python manage.py seed_slots [--doctor "Dr. Name"] [--date YYYY-MM-DD] [--clear]`

## Quick Start Guide

### 1. Run Migrations (Already configured)
```bash
python manage.py migrate
```

### 2. (Optional) Seed 15-Minute Slots
```bash
# Seeds 15-minute slots for all default doctors for today:
python manage.py seed_slots

# Or clear and reseed for a specific doctor & date:
python manage.py seed_slots --doctor "Dr. Sarah Jenkins" --date 2026-09-09 --clear
```

### 3. Run the Development Server
```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.

### 4. Run Automated Tests
```bash
python manage.py test dispatcher
```


