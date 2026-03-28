from django.urls import path
from .views import superadmin, admin_ops, analyst, finance, requester, client
from . import views

app_name = 'dashboard'

urlpatterns = [
    # Router
    path('', views.dashboard_router, name='router'),

    # Super Admin
    path('home/', superadmin.index, name='superadmin'),
    path('home/user/<int:pk>/toggle/', superadmin.user_toggle_active, name='superadmin_user_toggle'),
    path('home/member/<int:pk>/toggle/', superadmin.member_toggle_available, name='superadmin_member_toggle'),
    path('home/service/create/', superadmin.service_create, name='superadmin_service_create'),
    path('home/service/<uuid:pk>/delete/', superadmin.service_delete, name='superadmin_service_delete'),
    path('home/technique/create/', superadmin.technique_create, name='superadmin_technique_create'),
    path('home/technique/<int:pk>/delete/', superadmin.technique_delete, name='superadmin_technique_delete'),
    path('home/content/update/', superadmin.content_update, name='superadmin_content_update'),

    # Platform Admin (Operations)
    path('ops/', admin_ops.index, name='admin_ops'),
    path('ops/transition/<uuid:pk>/', admin_ops.transition_request, name='admin_transition'),
    path('ops/assign/<uuid:pk>/', admin_ops.assign_request, name='admin_assign'),
    path('ops/points/<int:pk>/', admin_ops.award_points, name='admin_award_points'),
    path('ops/cheer/<int:pk>/', admin_ops.send_cheer, name='admin_send_cheer'),
    path('ops/report/<uuid:pk>/', admin_ops.report_review, name='admin_report_review'),

    # Analyst
    path('analyst/', analyst.index, name='analyst'),
    path('analyst/accept/<uuid:pk>/', analyst.accept_task, name='analyst_accept'),
    path('analyst/decline/<uuid:pk>/', analyst.decline_task, name='analyst_decline'),
    path('analyst/action/<uuid:pk>/', analyst.workflow_action, name='analyst_action'),
    path('analyst/upload/<uuid:pk>/', analyst.upload_report, name='analyst_upload_report'),

    # Finance
    path('finance/', finance.index, name='finance'),
    path('finance/validate/<uuid:pk>/', finance.validate_budget, name='finance_validate'),

    # Requester (IBTIKAR)
    path('requester/', requester.index, name='requester'),
    path('requester/create/', requester.create_request, name='requester_create'),
    path('requester/confirm/<uuid:pk>/', requester.confirm_receipt, name='requester_confirm'),
    path('requester/rate/<uuid:pk>/', requester.rate_service, name='requester_rate'),

    # Client (GENOCLAB)
    path('client/', client.index, name='client'),
    path('client/create/', client.create_request, name='client_create'),
    path('client/quote/<uuid:pk>/accept/', client.accept_quote, name='client_accept_quote'),
    path('client/quote/<uuid:pk>/reject/', client.reject_quote, name='client_reject_quote'),
    path('client/confirm/<uuid:pk>/', client.confirm_receipt, name='client_confirm'),
    path('client/rate/<uuid:pk>/', client.rate_service, name='client_rate'),
]
