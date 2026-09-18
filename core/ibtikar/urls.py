from django.urls import path
from core.ibtikar import views

app_name = 'ibtikar'
urlpatterns = [
    path('request/<uuid:pk>/code/', views.submit_code, name='code'),
    path('guest/<uuid:token>/code/', views.submit_code, name='guest_code'),
    path('', views.index, name='index'),
    path('new/<str:code>/', views.editor, name='new'),
    path('request/<uuid:pk>/', views.detail, name='detail'),
    path('request/<uuid:pk>/edit/', views.editor, name='edit'),
    path('request/<uuid:pk>/staff/', views.staff_editor, name='staff'),
    path('guest/<uuid:token>/', views.detail, name='guest_detail'),
    path('guest/<uuid:token>/edit/', views.editor, name='guest_edit'),
    path('attachment/<uuid:pk>/', views.attachment, name='attachment'),
    path('estimate/<str:code>/', views.estimate, name='estimate'),
]
