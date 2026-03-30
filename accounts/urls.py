from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('profile/', views.profile, name='profile'),
    path('convert-guest/', views.convert_guest, name='convert_guest'),
    path('check-email/', views.check_email, name='check_email'),
    path('force-change-password/', views.force_change_password, name='force_change_password'),
]
