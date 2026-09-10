from django.urls import path
from . import views

app_name = 'dispatcher'

urlpatterns = [
    path('', views.daily_calendar_view, name='daily_calendar'),
    path('book/', views.book_calendar_slot, name='book_slot_post'),
    path(
        'book/<int:slot_id>/', views.book_calendar_slot,
        name='book_calendar_slot'),
    path(
        'cancel/<int:slot_id>/', views.cancel_calendar_slot,
        name='cancel_slot'),
    path('seed/', views.seed_slots_view, name='seed_slots'),
    path(
        'team/toggle/<int:member_id>/', views.toggle_team_member_status,
        name='toggle_team_member'),
    path('team/add/', views.add_team_member, name='add_team_member'),
    path('team/reset-password/<int:member_id>/', views.reset_team_member_password, name='reset_team_member_password'),
    path('team/reset-pw/<int:member_id>/', views.reset_team_member_password, name='reset_password'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]
