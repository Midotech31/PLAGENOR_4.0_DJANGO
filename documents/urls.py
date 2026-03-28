from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    path('ibtikar-form/<uuid:request_id>/', views.ibtikar_form_view, name='ibtikar_form'),
    path('platform-note/<uuid:request_id>/', views.platform_note_view, name='platform_note'),
    path('quote/<uuid:request_id>/', views.quote_view, name='quote'),
    path('reception-form/<uuid:request_id>/', views.reception_form_view, name='reception_form'),
]
