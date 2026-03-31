"""
PLAGENOR 4.0 - REST API
=======================
RESTful API for mobile app integration and third-party access.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Request, Service, Invoice
from accounts.models import User
from notifications.models import Notification

# =============================================================================
# API Views
# =============================================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def api_health(request):
    """Health check endpoint"""
    return Response({
        'status': 'healthy',
        'version': '4.0.0',
        'service': 'PLAGENOR API'
    })


class ServiceListView(APIView):
    """List all active services"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        services = Service.objects.filter(active=True).values(
            'id', 'code', 'name', 'description', 
            'ibtikar_price', 'genoclab_price', 
            'turnaround_days', 'channel_availability'
        )
        return Response(list(services))


class ServiceDetailView(APIView):
    """Get service details"""
    permission_classes = [AllowAny]
    
    def get(self, request, code):
        try:
            service = Service.objects.get(code=code, active=True)
            return Response({
                'id': str(service.id),
                'code': service.code,
                'name': service.name,
                'description': service.description,
                'ibtikar_price': str(service.ibtikar_price),
                'genoclab_price': str(service.genoclab_price),
                'turnaround_days': service.turnaround_days,
                'channel_availability': service.channel_availability,
                'service_type': service.service_type,
            })
        except Service.DoesNotExist:
            return Response({'error': 'Service not found'}, status=404)


class RequestListView(APIView):
    """List requests for authenticated user"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        requests = Request.objects.filter(
            requester=request.user
        ).select_related('service').order_by('-created_at')[:50].values(
            'id', 'display_id', 'title', 'status', 'channel',
            'created_at', 'updated_at'
        )
        return Response(list(requests))


class RequestDetailView(APIView):
    """Get request details"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        try:
            req = Request.objects.select_related(
                'service', 'requester', 'assigned_to__user'
            ).get(pk=pk)
            
            # Check if user has access
            if req.requester != request.user and not request.user.is_admin:
                return Response({'error': 'Access denied'}, status=403)
            
            return Response({
                'id': str(req.id),
                'display_id': req.display_id,
                'title': req.title,
                'description': req.description,
                'status': req.status,
                'channel': req.channel,
                'urgency': req.urgency,
                'service': req.service.name if req.service else None,
                'created_at': req.created_at.isoformat(),
                'updated_at': req.updated_at.isoformat(),
            })
        except Request.DoesNotExist:
            return Response({'error': 'Request not found'}, status=404)


class NotificationListView(APIView):
    """List notifications for authenticated user"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        notifications = Notification.objects.filter(
            user=request.user
        ).order_by('-created_at')[:20].values(
            'id', 'message', 'notification_type', 'read', 'created_at'
        )
        return Response(list(notifications))
    
    def post(self, request):
        """Mark notification as read"""
        notification_id = request.data.get('id')
        try:
            notification = Notification.objects.get(id=notification_id, user=request.user)
            notification.read = True
            notification.save()
            return Response({'status': 'success'})
        except Notification.DoesNotExist:
            return Response({'error': 'Notification not found'}, status=404)


class TrackRequestView(APIView):
    """Track request by display_id or guest token (public)"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        display_id = request.query_params.get('display_id')
        guest_token = request.query_params.get('token')
        
        if display_id:
            try:
                req = Request.objects.select_related('service').get(display_id=display_id)
            except Request.DoesNotExist:
                return Response({'error': 'Request not found'}, status=404)
        elif guest_token:
            try:
                req = Request.objects.select_related('service').get(guest_token=guest_token)
            except Request.DoesNotExist:
                return Response({'error': 'Request not found'}, status=404)
        else:
            return Response({'error': 'display_id or token required'}, status=400)
        
        return Response({
            'id': str(req.id),
            'display_id': req.display_id,
            'title': req.title,
            'status': req.status,
            'status_display': req.get_status_display(),
            'service': req.service.name if req.service else None,
            'updated_at': req.updated_at.isoformat(),
            'report_delivered': req.report_delivered,
        })


# =============================================================================
# URL Configuration
# =============================================================================

urlpatterns = [
    # Health check
    path('health/', api_health, name='api_health'),
    
    # Services
    path('services/', ServiceListView.as_view(), name='api_services'),
    path('services/<str:code>/', ServiceDetailView.as_view(), name='api_service_detail'),
    
    # Requests (authenticated)
    path('requests/', RequestListView.as_view(), name='api_requests'),
    path('requests/<uuid:pk>/', RequestDetailView.as_view(), name='api_request_detail'),
    
    # Notifications (authenticated)
    path('notifications/', NotificationListView.as_view(), name='api_notifications'),
    
    # Public tracking
    path('track/', TrackRequestView.as_view(), name='api_track'),
]
