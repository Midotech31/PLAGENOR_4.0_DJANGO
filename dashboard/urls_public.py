from django.urls import path
from . import views_public

urlpatterns = [
    path('', views_public.home, name='home'),
    path('about/', views_public.about, name='about'),
    path('services/', views_public.services, name='services'),
    path('contact/', views_public.contact, name='contact'),
    path('track/', views_public.track, name='track'),
    path('guest-submit/', views_public.guest_submit, name='guest_submit'),
]
