"""
Gunicorn configuration for PLAGENOR production deployment.
================================================================
This configuration is optimized for Django applications with HTMX.

Worker Configuration:
- workers: 2-4 x CPU cores (adjust based on server resources)
- worker_class: sync (default, use gevent for WebSockets)
- timeout: 120 seconds (allow for long-running requests)
- keepalive: 5 seconds

Performance Tuning:
- preload_app: True (load app before forking workers)
- max_requests: 1000 (recycle workers to prevent memory leaks)
- max_requests_jitter: 50 (randomize worker recycling)

Security:
- bind: Unix socket or localhost only (use nginx for public access)
- workers_run_on_sudo: False (security best practice)

Logging:
- Access logs: Captured by logging system
- Error logs: Sent to syslog or file
"""

import multiprocessing
import os
from pathlib import Path

# Server socket
bind = os.getenv('GUNICORN_BIND', '127.0.0.1:8000')
backlog = 2048

# Worker processes
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = os.getenv('GUNICORN_WORKER_CLASS', 'sync')
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 120
keepalive = 5

# Graceful timeout
graceful_timeout = 30

# Preload application
preload_app = True

# Process naming
proc_name = 'plagenor'

# Server mechanics
daemon = False
pidfile = None
umask = 0o027
user = None
group = None
tmp_upload_dir = None

# SSL (if terminating SSL at gunicorn)
# keyfile = '/path/to/key.pem'
# certfile = '/path/to/cert.pem'

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Request ID middleware integration
def pre_request(worker, req):
    """Add request ID to each request for tracing"""
    worker.log.debug("%s %s" % (req.method, req.path))

def post_request(worker, req, environ, resp):
    """Hook for post-request processing"""
    pass

# Server hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    pass

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    pass

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("PLAGENOR is ready. Listening on: %s" % bind)

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    pass

def post_worker_init(worker):
    """Called just after a worker has initialized the application."""
    pass

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    pass

def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    pass

def pre_exec(server):
    """Called just before a new master process is forked."""
    pass

def pre_shutdown(server):
    """Called just before serving on shutdown."""
    pass

def post_shutdown(server):
    """Called just after serving on shutdown."""
    pass

def child_exit(server, worker):
    """Called just after a worker has been exited, in the master process."""
    pass

def worker_exit(server, worker):
    """Called just after a worker has been exited, in the worker process."""
    pass

def nworkers_changed(server, new_value, old_value):
    """Called just after num_workers has been changed."""
    pass

def on_exit(server):
    """Called just before exiting Gunicorn."""
    pass
