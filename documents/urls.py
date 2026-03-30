from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    # Document generation (existing)
    path('ibtikar-form/<uuid:request_id>/', views.ibtikar_form_view, name='ibtikar_form'),
    path('platform-note/<uuid:request_id>/', views.platform_note_view, name='platform_note'),
    path('quote/<uuid:request_id>/', views.quote_view, name='quote'),
    path('reception-form/<uuid:request_id>/', views.reception_form_view, name='reception_form'),
    
    # Template management (new)
    path('templates/', views.template_list, name='template_list'),
    path('templates/create/', views.template_create, name='template_create'),
    path('templates/<int:pk>/', views.template_detail, name='template_detail'),
    path('templates/<int:pk>/edit/', views.template_edit, name='template_edit'),
    path('templates/<int:pk>/delete/', views.template_delete, name='template_delete'),
    path('templates/<int:pk>/toggle/', views.template_toggle_active, name='template_toggle'),
]
