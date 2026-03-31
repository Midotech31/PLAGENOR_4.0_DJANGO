"""
Rate limiting middleware for Django - Protects against brute force attacks
"""
import time
from collections import defaultdict
from django.http import JsonResponse
from django.conf import settings


class RateLimitMiddleware:
    """
    Rate limiting middleware that tracks requests per IP and path.
    Implements sliding window rate limiting with configurable limits.
    """
    
    # In-memory storage (use Redis for multi-process deployments)
    _requests = defaultdict(list)
    _lock = defaultdict(bool)
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Rate limit configuration (requests per window)
        self.limits = {
            'default': (100, 60),        # 100 requests per minute
            'auth': (10, 60),            # 10 requests per minute for auth endpoints
            'api': (60, 60),             # 60 requests per minute for API
            'upload': (20, 60),          # 20 requests per minute for uploads
        }
        
        # Paths that require stricter rate limiting
        self.auth_paths = [
            '/accounts/login/',
            '/accounts/password_reset/',
            '/accounts/register/',
        ]
        
        self.api_paths = [
            '/api/',
            '/dashboard/api/',
        ]
        
        self.upload_paths = [
            '/documents/upload/',
            '/core/upload/',
        ]
    
    def __call__(self, request):
        # Get client IP
        ip = self._get_client_ip(request)
        path = request.path
        
        # Determine rate limit category
        limit_type = 'default'
        for auth_path in self.auth_paths:
            if path.startswith(auth_path):
                limit_type = 'auth'
                break
        for api_path in self.api_paths:
            if path.startswith(api_path):
                limit_type = 'api'
                break
        for upload_path in self.upload_paths:
            if path.startswith(upload_path):
                limit_type = 'upload'
                break
        
        max_requests, window = self.limits[limit_type]
        
        # Check rate limit
        if not self._check_rate_limit(ip, max_requests, window):
            return JsonResponse({
                'error': 'Too many requests',
                'retry_after': window
            }, status=429)
        
        response = self.get_response(request)
        
        # Add rate limit headers
        remaining = max_requests - self._get_request_count(ip)
        response['X-RateLimit-Limit'] = str(max_requests)
        response['X-RateLimit-Remaining'] = str(max(0, remaining))
        response['X-RateLimit-Window'] = str(window)
        
        return response
    
    def _get_client_ip(self, request):
        """Extract client IP from request, considering proxies"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')
    
    def _check_rate_limit(self, ip, max_requests, window):
        """Check if request is within rate limit"""
        now = time.time()
        key = f"{ip}:{window}"
        
        # Remove old requests outside the window
        self._requests[key] = [
            req_time for req_time in self._requests[key]
            if now - req_time < window
        ]
        
        # Check if limit exceeded
        if len(self._requests[key]) >= max_requests:
            return False
        
        # Add current request
        self._requests[key].append(now)
        return True
    
    def _get_request_count(self, ip):
        """Get current request count for IP"""
        key = f"{ip}:60"  # Default window
        now = time.time()
        return len([
            req_time for req_time in self._requests[key]
            if now - req_time < 60
        ])


class BruteForceProtectionMiddleware:
    """
    Track failed login attempts to prevent brute force attacks.
    """
    
    _failed_attempts = defaultdict(list)
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.max_attempts = 5  # Max failed attempts before lockout
        self.lockout_duration = 900  # 15 minutes lockout
        self.window = 3600  # Track attempts over 1 hour
    
    def __call__(self, request):
        # Only check on login POST requests
        if request.method == 'POST' and '/accounts/login/' in request.path:
            ip = self._get_client_ip(request)
            
            if self._is_locked_out(ip):
                return JsonResponse({
                    'error': 'Account temporarily locked due to too many failed login attempts',
                    'retry_after': self.lockout_duration
                }, status=429)
        
        response = self.get_response(request)
        return response
    
    def _get_client_ip(self, request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')
    
    def _is_locked_out(self, ip):
        """Check if IP is locked out"""
        now = time.time()
        key = f"lockout:{ip}"
        
        # Check if currently locked
        if self._failed_attempts.get(key):
            lockout_time = self._failed_attempts[key]
            if now < lockout_time:
                return True
        
        # Clean up old attempts
        attempts_key = f"attempts:{ip}"
        self._failed_attempts[attempts_key] = [
            attempt for attempt in self._failed_attempts.get(attempts_key, [])
            if now - attempt < self.window
        ]
        
        return False
    
    @classmethod
    def record_failed_attempt(cls, ip):
        """Record a failed login attempt"""
        now = time.time()
        attempts_key = f"attempts:{ip}"
        lockout_key = f"lockout:{ip}"
        
        # Add failed attempt
        if attempts_key not in cls._failed_attempts:
            cls._failed_attempts[attempts_key] = []
        cls._failed_attempts[attempts_key].append(now)
        
        # Check if should lock out
        if len(cls._failed_attempts[attempts_key]) >= 5:
            cls._failed_attempts[lockout_key] = now + 900  # 15 minute lockout
    
    @classmethod
    def clear_attempts(cls, ip):
        """Clear failed attempts after successful login"""
        cls._failed_attempts.pop(f"attempts:{ip}", None)
        cls._failed_attempts.pop(f"lockout:{ip}", None)
