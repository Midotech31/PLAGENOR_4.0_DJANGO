from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse

from dashboard.views import report as report_views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

# Health check endpoint for uptime monitoring
def health_check(request):
    return JsonResponse({
        'status': 'ok',
        'version': '4.0.0',
        'debug': settings.DEBUG,
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('documents/', include('documents.urls')),
    path('notifications/', include('notifications.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    
    # Health check endpoint for uptime monitoring
    path('health/', health_check, name='health_check'),
    
    # REST API
    path('api/v1/', include('api.urls')),
    
    # OpenAPI Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # Public report delivery
    path('report/<uuid:token>/', report_views.report_viewer, name='report_view'),
    path('report/<uuid:token>/detail/', report_views.report_detail_viewer, name='report_detail_view'),
    path('report/<uuid:token>/download/', report_views.download_report, name='report_download'),
    path('report/<uuid:token>/rate/', report_views.rate_report, name='report_rate'),
    path('report/<uuid:token>/acknowledge/', report_views.acknowledge_citation, name='report_acknowledge'),
    
    # Public pages
    path('', include('dashboard.urls_public')),
]

# Serve static files in production
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
