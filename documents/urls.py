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

    # Document block management (Phase 3.7)
    path('blocks/', views.block_list, name='block_list'),
    path('blocks/create/', views.block_create, name='block_create'),
    path('blocks/<int:pk>/edit/', views.block_edit, name='block_edit'),
    path('blocks/<int:pk>/delete/', views.block_delete, name='block_delete'),
    path('blocks/<int:pk>/toggle/', views.block_toggle_active, name='block_toggle'),
]
