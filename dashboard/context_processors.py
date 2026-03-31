from notifications.models import Notification
from core.models import Request


def notifications(request):
    if request.user.is_authenticated:
        unread = Notification.objects.filter(user=request.user, read=False)
        context = {
            'unread_count': unread.count(),
            'recent_notifications': unread.order_by('-created_at')[:10],
        }
        
        # Add admin badge counts for PLATFORM_ADMIN
        if request.user.role == 'PLATFORM_ADMIN':
            # Pending requests count
            context['pending_count'] = Request.objects.filter(
                status__in=['SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'REPORT_UPLOADED', 'ADMIN_REVIEW']
            ).count()
            
            # Validation requests count
            context['validation_count'] = Request.objects.filter(
                status__in=['SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE']
            ).count()
            
            # Assignable requests count
            context['assignable_count'] = Request.objects.filter(
                status__in=['IBTIKAR_CODE_SUBMITTED', 'PAYMENT_CONFIRMED', 'ORDER_UPLOADED']
            ).count()
            
            # Report review count
            context['review_count'] = Request.objects.filter(
                status__in=['REPORT_UPLOADED', 'ADMIN_REVIEW']
            ).count()
        
        return context
    return {}
