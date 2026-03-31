from django.urls import path
from .views import superadmin, admin_ops, analyst, finance, requester, client, messaging, service_form_api, qrcode_view
from . import views

app_name = 'dashboard'

urlpatterns = [
    # Router
    path('', views.dashboard_router, name='router'),

    # Super Admin
    path('home/', superadmin.index, name='superadmin'),
    path('home/user/<int:pk>/toggle/', superadmin.user_toggle_active, name='superadmin_user_toggle'),
    path('home/member/<int:pk>/toggle/', superadmin.member_toggle_available, name='superadmin_member_toggle'),
    path('home/member/<int:pk>/techniques/', superadmin.member_assign_techniques, name='superadmin_member_techniques'),
    path('home/service/create/', superadmin.service_create, name='superadmin_service_create'),
    path('home/service/<uuid:pk>/delete/', superadmin.service_delete, name='superadmin_service_delete'),
    path('home/service/<uuid:pk>/reactivate/', superadmin.service_reactivate, name='superadmin_service_reactivate'),
    path('home/technique/create/', superadmin.technique_create, name='superadmin_technique_create'),
    path('home/technique/<int:pk>/delete/', superadmin.technique_delete, name='superadmin_technique_delete'),
    path('home/technique/<int:pk>/edit/', superadmin.technique_edit, name='superadmin_technique_edit'),
    path('home/technique/<int:pk>/reactivate/', superadmin.technique_reactivate, name='superadmin_technique_reactivate'),
    path('home/content/update/', superadmin.content_update, name='superadmin_content_update'),
    path('home/content/<str:pk>/delete/', superadmin.content_delete, name='superadmin_content_delete'),
    path('home/service/<uuid:pk>/edit/', superadmin.service_edit, name='superadmin_service_edit'),
    path('home/template/<str:template_type>/download/', superadmin.download_template, name='superadmin_template_download'),
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
    path('home/user/<int:pk>/reset/', superadmin.reset_account, name='superadmin_reset_account'),
    path('home/request/<uuid:pk>/detail/', superadmin.request_detail, name='superadmin_request_detail'),
    path('home/request/<uuid:pk>/assign/', superadmin.assign_request_direct, name='superadmin_request_assign'),

    # Platform Admin (Operations)
    path('ops/', admin_ops.index, name='admin_ops'),
    path('ops/request/<uuid:pk>/', admin_ops.request_detail, name='admin_request_detail'),
    path('ops/transition/<uuid:pk>/', admin_ops.transition_request, name='admin_transition'),
    path('ops/assign/<uuid:pk>/', admin_ops.assign_request, name='admin_assign'),
    path('ops/points/<int:member_pk>/', admin_ops.award_points, name='admin_award_points'),
    path('ops/cheer/<int:member_pk>/', admin_ops.send_cheer, name='admin_send_cheer'),
    path('ops/gift/<int:member_pk>/', admin_ops.upload_gift, name='admin_upload_gift'),
    path('ops/report/<uuid:pk>/', admin_ops.report_review, name='admin_report_review'),
    path('ops/cost/<uuid:pk>/', admin_ops.adjust_cost, name='admin_adjust_cost'),
    path('ops/appointment/<uuid:pk>/', admin_ops.modify_appointment, name='admin_modify_appointment'),
    path('ops/quote/<uuid:pk>/', admin_ops.prepare_quote, name='admin_prepare_quote'),
    path('ops/invoice/<uuid:pk>/', admin_ops.generate_invoice, name='admin_generate_invoice'),
    path('ops/payment/<uuid:pk>/', admin_ops.confirm_payment, name='admin_confirm_payment'),
    
    # Activity Log (Task 1)
    path('ops/activity-log/', admin_ops.activity_log, name='admin_activity_log'),
    
    # Notifications API (Task 2)
    path('ops/notifications/', admin_ops.notifications_api, name='admin_notifications_api'),
    
    # User Oversight (Task 3)
    path('ops/users/', admin_ops.users_list, name='admin_users_list'),
    path('ops/user/<int:pk>/', admin_ops.user_detail, name='admin_user_detail'),
    
    # Bulk Actions (Task 6)
    path('ops/bulk-action/', admin_ops.bulk_action, name='admin_bulk_action'),
    
    # CSV Export (Task 6)
    path('ops/export-csv/', admin_ops.export_requests_csv, name='admin_export_csv'),
    
    # Performance & Points (Task 7)
    path('ops/performance/', admin_ops.performance_points, name='admin_performance'),
    path('ops/member/<int:member_pk>/points/', admin_ops.member_points_detail, name='admin_member_points'),

    # Analyst
    path('analyst/', analyst.index, name='analyst'),
    path('analyst/accept/<uuid:pk>/', analyst.accept_task, name='analyst_accept'),
    path('analyst/decline/<uuid:pk>/', analyst.decline_task, name='analyst_decline'),
    path('analyst/action/<uuid:pk>/', analyst.workflow_action, name='analyst_action'),
    path('analyst/upload/<uuid:pk>/', analyst.upload_report, name='analyst_upload_report'),
    path('analyst/appointment/<uuid:pk>/', analyst.suggest_appointment, name='analyst_suggest_appointment'),
    path('analyst/alt-date/<uuid:pk>/accept/', analyst.accept_alt_date, name='analyst_accept_alt_date'),
    path('analyst/alt-date/<uuid:pk>/decline/', analyst.decline_alt_date, name='analyst_decline_alt_date'),
    path('analyst/request/<uuid:pk>/', analyst.request_detail, name='analyst_request_detail'),
    path('analyst/collect-gift/', analyst.collect_gift, name='analyst_collect_gift'),

    # Finance
    path('finance/', finance.index, name='finance'),
    path('finance/validate/<uuid:pk>/', finance.validate_budget, name='finance_validate'),
    path('finance/payment/<uuid:pk>/', finance.update_payment_status, name='finance_payment_status'),

    # Requester (IBTIKAR)
    path('requester/', requester.index, name='requester'),
    path('requester/request/<uuid:pk>/', requester.request_detail, name='requester_request_detail'),
    path('requester/create/', requester.create_request, name='requester_create'),
    path('requester/confirm/<uuid:pk>/', requester.confirm_receipt, name='requester_confirm'),
    path('requester/rate/<uuid:pk>/', requester.rate_service, name='requester_rate'),
    path('requester/appointment/<uuid:pk>/confirm/', requester.confirm_appointment, name='requester_confirm_appointment'),
    path('requester/ibtikar-code/<uuid:pk>/', requester.submit_ibtikar_code, name='requester_ibtikar_code'),
    path('requester/alt-date/<uuid:pk>/', requester.suggest_alternative_date, name='requester_alt_date'),

    # Client (GENOCLAB)
    path('client/', client.index, name='client'),
    path('client/request/<uuid:pk>/', client.request_detail, name='client_request_detail'),
    path('client/create/', client.create_request, name='client_create'),
    path('client/quote/<uuid:pk>/accept/', client.accept_quote, name='client_accept_quote'),
    path('client/quote/<uuid:pk>/reject/', client.reject_quote, name='client_reject_quote'),
    path('client/order/<uuid:pk>/upload/', client.upload_order, name='client_upload_order'),
    path('client/payment/<uuid:pk>/upload/', client.upload_payment_receipt, name='client_upload_payment'),
    path('client/appointment/<uuid:pk>/confirm/', client.confirm_appointment, name='client_confirm_appointment'),
    path('client/confirm/<uuid:pk>/', client.confirm_receipt, name='client_confirm'),
    path('client/rate/<uuid:pk>/', client.rate_service, name='client_rate'),
    path('client/alt-date/<uuid:pk>/', client.suggest_alternative_date, name='client_alt_date'),

    # Service form API
    path('api/service-form/<str:service_code>/', service_form_api.service_form_fragment, name='service_form_fragment'),

    # QR Code
    path('qr/<uuid:pk>/', qrcode_view.report_qr, name='report_qr'),

    # Messaging
    path('message/<uuid:pk>/', messaging.send_message, name='send_message'),

    # Audit Log (SUPER_ADMIN)
    path('audit-log/', superadmin.audit_log, name='audit_log'),

    # Revenue Archives (SUPER_ADMIN)
    path('revenue-archives/', superadmin.revenue_archives, name='revenue_archives'),
]
