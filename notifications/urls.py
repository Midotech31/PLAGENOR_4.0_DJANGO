from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('<int:pk>/click/', views.notification_click, name='click'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
]
