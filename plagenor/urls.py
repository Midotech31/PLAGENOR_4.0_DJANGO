from django.contrib import admin
from django.urls import path, include
from django.views.i18n import JavaScriptCatalog

from dashboard.views import report as report_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('documents/', include('documents.urls')),
    path('notifications/', include('notifications.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    # JavaScript translation catalog — frontend code uses gettext() in JS.
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
    # Public report delivery
    path('report/<uuid:token>/', report_views.report_viewer, name='report_view'),
    path('report/<uuid:token>/delivered/', report_views.mark_report_delivered, name='report_mark_delivered'),
    path('report/<uuid:token>/rate/', report_views.rate_report, name='report_rate'),
    path('report/<uuid:token>/acknowledge/', report_views.acknowledge_citation, name='report_acknowledge'),
    path('report/<uuid:token>/download/', report_views.download_report, name='report_download'),
    # Gate raw report files: /media/reports/<file> goes through the citation
    # clause. Declared BEFORE the generic media handler so it wins.
    path('media/reports/<path:path>', report_views.protected_report_media,
         name='protected_report_media'),
    # All other uploaded media is streamed from the storage backend (Supabase
    # Storage in prod, local FS in dev). MEDIA_ROOT is not web-served in
    # production and the bucket is private, so Django streams the bytes.
    path('media/<path:path>', report_views.serve_media, name='serve_media'),
    path('', include('dashboard.urls_public')),
]
