# plagenor/request_id.py
# Request ID middleware for production debugging
# Adds X-Request-ID header to all responses and logs with request ID

import uuid
import logging
import threading
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('plagenor.request_id')

# Thread-local storage for request ID
_request_id = threading.local()


def get_request_id():
    """Get current request ID from thread-local storage"""
    return getattr(_request_id, 'request_id', None)


class RequestIDMiddleware(MiddlewareMixin):
    """
    Middleware that:
    1. Generates unique request ID for each request
    2. Stores in thread-local for access anywhere in the code
    3. Adds X-Request-ID header to response
    4. Logs request ID for all POST/PUT/PATCH operations
    """
    
    def process_request(self, request):
        # Generate or use existing request ID
        request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        _request_id.request_id = request_id
        request.request_id = request_id
        
        # Log all requests with request ID
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            logger.info(
                f"[{request_id}] {request.method} {request.path}",
                extra={
                    'request_id': request_id,
                    'method': request.method,
                    'path': request.path,
                    'user_id': request.user.id if request.user.is_authenticated else None,
                    'user_role': getattr(request.user, 'role', None),
                    'ip': self._get_client_ip(request),
                }
            )
    
    def process_response(self, request, response):
        # Add request ID to response headers
        request_id = getattr(request, 'request_id', None)
        if request_id:
            response['X-Request-ID'] = request_id
        
        # Log response with request ID
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            logger.info(
                f"[{request_id}] {request.method} {request.path} -> {response.status_code}",
                extra={
                    'request_id': request_id,
                    'status_code': response.status_code,
                }
            )
        
        return response
    
    def _get_client_ip(self, request):
        """Extract client IP from request headers"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')
