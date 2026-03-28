from django.urls import path
from . import views_public

urlpatterns = [
    path('', views_public.home, name='home'),
    path('about/', views_public.about, name='about'),
    path('services/', views_public.services, name='services'),
    path('track/', views_public.track, name='track'),
]
