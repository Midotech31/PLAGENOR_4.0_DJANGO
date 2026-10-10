from django.contrib.admin.apps import AdminConfig


class PlagenorAdminConfig(AdminConfig):
    default_site = 'plagenor.admin.SystemAdminSite'
