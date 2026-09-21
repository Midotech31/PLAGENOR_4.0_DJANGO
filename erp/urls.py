from django.urls import path
from . import views

app_name = 'erp'
urlpatterns = [
    path('', views.index, name='index'),
    path('locations/<uuid:pk>/', views.location_detail, name='location'),
    path('audit/', views.audit_trail, name='audit'),
    path('articles/<uuid:pk>/', views.article_detail, name='article'),
    path('articles/<uuid:pk>/price/', views.price_create, name='price'),
    path('articles/<uuid:article_id>/conversions/new/', views.conversion_edit, name='conversion_new'),
    path('articles/<uuid:article_id>/conversions/<uuid:pk>/', views.conversion_edit, name='conversion_edit'),
    path('<slug:section>/', views.record_list, name='list'),
    path('<slug:section>/new/', views.record_edit, name='create'),
    path('<slug:section>/<uuid:pk>/edit/', views.record_edit, name='edit'),
]
