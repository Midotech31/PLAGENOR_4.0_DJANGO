"""
PLAGENOR Celery Configuration
=============================
Async task processing for heavy operations like:
- Document generation
- Email sending
- Report processing
- Data exports
"""

import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')

# Create Celery app
app = Celery('plagenor')

# Load config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# =============================================================================
# CELERY CONFIGURATION
# =============================================================================

# Message broker (Redis)
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

app.conf.update(
    # Broker
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,
    
    # Serialization
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    
    # Timezones
    timezone='Africa/Algiers',
    enable_utc=True,
    
    # Task routing
    task_routes={
        'notifications.tasks.*': {'queue': 'notifications'},
        'documents.tasks.*': {'queue': 'documents'},
        'core.tasks.*': {'queue': 'core'},
    },
    
    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes
    
    # Worker
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
    
    # Result backend
    result_expires=3600,  # 1 hour
    result_persistent=True,
    
    # Beat schedule for periodic tasks
    beat_schedule={
        'cleanup-old-sessions': {
            'task': 'core.tasks.cleanup_old_sessions',
            'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
        },
        'send-daily-digest': {
            'task': 'notifications.tasks.send_daily_digest',
            'schedule': crontab(hour=8, minute=0),  # Daily at 8 AM
        },
        'archive-old-requests': {
            'task': 'core.tasks.archive_old_requests',
            'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
        },
        'check-pending-notifications': {
            'task': 'notifications.tasks.check_pending_notifications',
            'schedule': crontab(minute='*/15'),  # Every 15 minutes
        },
    },
)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery"""
    print(f'Request: {self.request!r}')


# =============================================================================
# TASK EXAMPLES
# =============================================================================

@app.task(bind=True)
def send_email_task(self, to_email, subject, template_name, context):
    """
    Async email sending task
    Usage: send_email_task.delay('user@example.com', 'Subject', 'template.html', {'name': 'User'})
    """
    from notifications.emails import send_email
    try:
        send_email(
            to=[to_email],
            subject=subject,
            template_name=template_name,
            context=context
        )
        return {'status': 'success', 'to': to_email}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@app.task(bind=True)
def generate_document_task(self, request_id, document_type):
    """
    Async document generation
    Usage: generate_document_task.delay(request_id, 'report')
    """
    from documents.generators import generate_request_document
    try:
        result = generate_request_document(request_id, document_type)
        return {'status': 'success', 'result': result}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@app.task(bind=True)
def export_data_task(self, export_type, filters):
    """
    Async data export
    Usage: export_data_task.delay('requests', {'status': 'COMPLETED'})
    """
    import json
    from datetime import datetime
    
    try:
        # This is a placeholder - implement based on your export needs
        filename = f"export_{export_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Your export logic here
        # result = perform_export(export_type, filters)
        
        return {
            'status': 'success',
            'filename': filename,
            'download_url': f'/media/exports/{filename}'
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@app.task(bind=True)
def send_notification_task(self, user_id, notification_type, message, **kwargs):
    """
    Async notification sending
    Usage: send_notification_task.delay(user_id, 'WORKFLOW', 'Your request was updated')
    """
    from notifications.models import Notification
    from django.contrib.auth import get_user_model
    
    try:
        user = get_user_model().objects.get(id=user_id)
        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            message=message,
            **{k: v for k, v in kwargs.items() if k in ['request', 'link']}
        )
        return {'status': 'success', 'notification_id': notification.id}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}
