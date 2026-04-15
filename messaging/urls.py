from django.urls import path
from messaging import views

urlpatterns = [
    path('request/<uuid:pk>/messages/', views.request_messages, name='request_messages'),
    path('request/<uuid:pk>/messages/history/', views.request_message_history, name='request_message_history'),
    path('reminders/', views.my_reminders, name='my_reminders'),
    path('reminder/<uuid:pk>/acknowledge/', views.acknowledge_reminder, name='acknowledge_reminder'),
]
