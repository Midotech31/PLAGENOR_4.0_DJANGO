# documents/urls.py — PLAGENOR 4.0 Document URLs

from django.urls import path
from documents import views

app_name = 'documents'

urlpatterns = [
    # PDF Download Views
    path('ibtikar-form/<uuid:pk>/', views.ibtikar_form_pdf, name='ibtikar_form_pdf'),
    path('ibtikar-form-download/<uuid:pk>/', views.download_ibtikar_form, name='ibtikar_form_download'),
    path('platform-note/<uuid:pk>/', views.download_platform_note, name='platform_note'),
    path('reception-form/<uuid:pk>/', views.download_reception_form, name='reception_form'),
    
    # PDF Regeneration (Admin Only)
    path('regenerate/<uuid:pk>/<str:doc_type>/', views.regenerate_pdf, name='regenerate_pdf'),
    
    # Legacy/Deprecated Views (redirects)
    path('ibtikar/<uuid:request_id>/', views.ibtikar_form_view, name='ibtikar_form_legacy'),
    path('platform_note/<uuid:request_id>/', views.platform_note_view, name='platform_note_legacy'),
    path('reception/<uuid:request_id>/', views.reception_form_view, name='reception_form_legacy'),
    
    # Status Check API
    path('status/<uuid:pk>/', views.check_pdf_status, name='pdf_status'),
]
