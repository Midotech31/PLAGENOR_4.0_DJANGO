from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_router, name='router'),
    # Placeholder for all role-specific dashboards (to be implemented)
    path('home/', views.placeholder_dashboard, name='superadmin'),
    path('ops/', views.placeholder_dashboard, name='admin_ops'),
    path('analyst/', views.placeholder_dashboard, name='analyst'),
    path('finance/', views.placeholder_dashboard, name='finance'),
    path('requester/', views.placeholder_dashboard, name='requester'),
    path('client/', views.placeholder_dashboard, name='client'),
    path('placeholder/', views.placeholder_dashboard, name='placeholder'),
]
