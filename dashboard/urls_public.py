from django.urls import path
from . import views_public

urlpatterns = [
    path('', views_public.home, name='home'),
    path('about/', views_public.about, name='about'),
    path('services/', views_public.services, name='services'),
    path('contact/', views_public.contact, name='contact'),
    path('track/', views_public.track, name='track'),
    path('guest-submit/', views_public.guest_submit, name='guest_submit'),
    path('track/ibtikar-code/<uuid:pk>/', views_public.guest_ibtikar_code, name='guest_ibtikar_code'),
    path('service/<str:service_code>/detail/', views_public.service_detail, name='service_detail'),
    path('service/<str:service_code>/', views_public.service_landing, name='service_landing'),
    path('switch-language/', views_public.switch_language, name='switch_language'),
]
