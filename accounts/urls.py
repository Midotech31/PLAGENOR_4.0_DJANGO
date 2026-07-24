from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('profile/', views.profile, name='profile'),
    path('convert-guest/', views.convert_guest, name='convert_guest'),
    path('convert-guest/verify/<str:token>/', views.convert_guest_verify, name='convert_guest_verify'),
    path('check-email/', views.check_email, name='check_email'),
    path('force-change-password/', views.force_change_password, name='force_change_password'),
    # Self-service password reset (Django-native token flow).
    path('password-reset/', views.ForgotPasswordView.as_view(), name='password_reset'),
    path('password-reset/done/', views.ForgotPasswordDoneView.as_view(), name='password_reset_done'),
    path('password-reset/confirm/<uidb64>/<token>/', views.ForgotPasswordConfirmView.as_view(), name='password_reset_confirm'),
    path('password-reset/complete/', views.ForgotPasswordCompleteView.as_view(), name='password_reset_complete'),
    # Two-factor authentication (TOTP, opt-in).
    path('2fa/verify/', views.two_factor_verify, name='two_factor_verify'),
    path('2fa/setup/', views.two_factor_setup, name='two_factor_setup'),
    path('2fa/disable/', views.two_factor_disable, name='two_factor_disable'),
]
