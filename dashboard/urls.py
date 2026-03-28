from django.urls import path
from .views import superadmin, admin_ops, analyst, finance, requester, client, messaging, service_form_api
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
    path('home/service/<uuid:pk>/edit/', superadmin.service_edit, name='superadmin_service_edit'),
    path('home/backup/', superadmin.backup_now, name='superadmin_backup'),
    path('home/user/create/', superadmin.create_user, name='superadmin_user_create'),
    path('home/user/<int:pk>/edit/', superadmin.user_edit, name='superadmin_user_edit'),
    path('home/force-transition/<uuid:pk>/', superadmin.force_transition_view, name='superadmin_force_transition'),
    path('home/budget-override/<uuid:pk>/', superadmin.budget_override_view, name='superadmin_budget_override'),
    path('home/payment-method/create/', superadmin.add_payment_method, name='superadmin_payment_method_create'),
    path('home/template-upload/', superadmin.upload_template, name='superadmin_template_upload'),
    path('home/reset-revenue/', superadmin.reset_revenue, name='superadmin_reset_revenue'),
    path('home/restore/', superadmin.restore_db, name='superadmin_restore'),
    path('home/export-emails/', superadmin.export_emails, name='superadmin_export_emails'),

    # Platform Admin (Operations)
    path('ops/', admin_ops.index, name='admin_ops'),
    path('ops/request/<uuid:pk>/', admin_ops.request_detail, name='admin_request_detail'),
    path('ops/transition/<uuid:pk>/', admin_ops.transition_request, name='admin_transition'),
    path('ops/assign/<uuid:pk>/', admin_ops.assign_request, name='admin_assign'),
    path('ops/points/<int:pk>/', admin_ops.award_points, name='admin_award_points'),
    path('ops/cheer/<int:pk>/', admin_ops.send_cheer, name='admin_send_cheer'),
    path('ops/report/<uuid:pk>/', admin_ops.report_review, name='admin_report_review'),
    path('ops/cost/<uuid:pk>/', admin_ops.adjust_cost, name='admin_adjust_cost'),
    path('ops/appointment/<uuid:pk>/', admin_ops.modify_appointment, name='admin_modify_appointment'),

    # Analyst
    path('analyst/', analyst.index, name='analyst'),
    path('analyst/accept/<uuid:pk>/', analyst.accept_task, name='analyst_accept'),
    path('analyst/decline/<uuid:pk>/', analyst.decline_task, name='analyst_decline'),
    path('analyst/action/<uuid:pk>/', analyst.workflow_action, name='analyst_action'),
    path('analyst/upload/<uuid:pk>/', analyst.upload_report, name='analyst_upload_report'),
    path('analyst/appointment/<uuid:pk>/', analyst.suggest_appointment, name='analyst_suggest_appointment'),
    path('analyst/request/<uuid:pk>/', analyst.request_detail, name='analyst_request_detail'),

    # Finance
    path('finance/', finance.index, name='finance'),
    path('finance/validate/<uuid:pk>/', finance.validate_budget, name='finance_validate'),
    path('finance/payment/<uuid:pk>/', finance.update_payment_status, name='finance_payment_status'),

    # Requester (IBTIKAR)
    path('requester/', requester.index, name='requester'),
    path('requester/create/', requester.create_request, name='requester_create'),
    path('requester/confirm/<uuid:pk>/', requester.confirm_receipt, name='requester_confirm'),
    path('requester/rate/<uuid:pk>/', requester.rate_service, name='requester_rate'),
    path('requester/appointment/<uuid:pk>/confirm/', requester.confirm_appointment, name='requester_confirm_appointment'),
    path('requester/alt-date/<uuid:pk>/', requester.suggest_alternative_date, name='requester_alt_date'),

    # Client (GENOCLAB)
    path('client/', client.index, name='client'),
    path('client/create/', client.create_request, name='client_create'),
    path('client/quote/<uuid:pk>/accept/', client.accept_quote, name='client_accept_quote'),
    path('client/quote/<uuid:pk>/reject/', client.reject_quote, name='client_reject_quote'),
    path('client/appointment/<uuid:pk>/confirm/', client.confirm_appointment, name='client_confirm_appointment'),
    path('client/confirm/<uuid:pk>/', client.confirm_receipt, name='client_confirm'),
    path('client/rate/<uuid:pk>/', client.rate_service, name='client_rate'),
    path('client/alt-date/<uuid:pk>/', client.suggest_alternative_date, name='client_alt_date'),

    # Service form API
    path('api/service-form/<str:service_code>/', service_form_api.service_form_fragment, name='service_form_fragment'),

    # Messaging
    path('message/<uuid:pk>/', messaging.send_message, name='send_message'),

    # Audit Log (SUPER_ADMIN)
    path('audit-log/', superadmin.audit_log, name='audit_log'),

    # Revenue Archives (SUPER_ADMIN)
    path('revenue-archives/', superadmin.revenue_archives, name='revenue_archives'),
]
