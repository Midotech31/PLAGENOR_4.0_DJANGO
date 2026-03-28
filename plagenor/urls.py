from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from dashboard.views import report as report_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    # Public report delivery
    path('report/<uuid:token>/', report_views.report_viewer, name='report_view'),
    path('report/<uuid:token>/rate/', report_views.rate_report, name='report_rate'),
    path('', include('dashboard.urls_public')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
