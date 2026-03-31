#!/usr/bin/env python3
"""
Automated Database Backup Script for PLAGENOR
==============================================
This script performs automated backups of the PLAGENOR database and media files.
It supports PostgreSQL and SQLite databases.

Usage:
    python scripts/backup_automated.py                    # Local backup
    python scripts/backup_automated.py --remote           # Upload to remote storage
    python scripts/backup_automated.py --config path.yml  # Use custom config

Cron Job Setup (daily at 2 AM):
    0 2 * * * cd /path/to/plagenor && python manage.py backup_db

Environment Variables:
    BACKUP_PATH      - Directory to store backups (default: ./backups)
    BACKUP_RETENTION - Number of days to keep backups (default: 30)
    DATABASE_URL     - Database connection string
"""

import os
import sys
import json
import gzip
import shutil
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
BACKUP_DIR = Path(os.getenv('BACKUP_PATH', './backups'))
RETENTION_DAYS = int(os.getenv('BACKUP_RETENTION', '30'))
COMPRESSION_LEVEL = 9  # Maximum compression

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'


def log(message, level='INFO'):
    """Log message with timestamp and level"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    color = {
        'INFO': Colors.BLUE,
        'SUCCESS': Colors.GREEN,
        'WARNING': Colors.YELLOW,
        'ERROR': Colors.RED,
    }.get(level, Colors.END)
    print(f"{color}[{timestamp}] [{level}] {message}{Colors.END}")


def get_backup_filename(prefix='plagenor', extension='sql'):
    """Generate timestamped backup filename"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{prefix}_{timestamp}.{extension}"


def ensure_backup_directory():
    """Create backup directory if it doesn't exist"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    (BACKUP_DIR / 'database').mkdir(exist_ok=True)
    (BACKUP_DIR / 'media').mkdir(exist_ok=True)
    (BACKUP_DIR / 'logs').mkdir(exist_ok=True)
    log(f"Backup directory ready: {BACKUP_DIR}", 'SUCCESS')


def get_database_type():
    """Determine database type from DATABASE_URL"""
    database_url = os.getenv('DATABASE_URL', '')
    
    if not database_url:
        return 'sqlite'
    
    if 'postgres' in database_url or 'postgresql' in database_url:
        return 'postgresql'
    elif 'mysql' in database_url:
        return 'mysql'
    elif 'sqlite' in database_url:
        return 'sqlite'
    
    return 'unknown'


def backup_postgresql(backup_file):
    """Backup PostgreSQL database using pg_dump"""
    database_url = os.getenv('DATABASE_URL')
    
    # Parse DATABASE_URL for pg_dump
    # Format: postgresql://user:password@host:port/database
    try:
        from urllib.parse import urlparse
        parsed = urlparse(database_url)
        
        user = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port or 5432
        database = parsed.path.lstrip('/')
        
        # Set PGPASSWORD environment variable
        env = os.environ.copy()
        env['PGPASSWORD'] = password
        
        # Run pg_dump
        cmd = [
            'pg_dump',
            '-h', host,
            '-p', str(port),
            '-U', user,
            '-d', database,
            '-F', 'c',  # Custom format for compression
            '-f', str(backup_file),
        ]
        
        log(f"Running pg_dump for PostgreSQL database...")
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            log(f"pg_dump failed: {result.stderr}", 'ERROR')
            return False
        
        log(f"PostgreSQL backup created: {backup_file}", 'SUCCESS')
        return True
        
    except Exception as e:
        log(f"PostgreSQL backup failed: {str(e)}", 'ERROR')
        return False


def backup_sqlite(backup_file):
    """Backup SQLite database by copying file"""
    # Find SQLite database file
    base_dir = Path(__file__).resolve().parent.parent
    db_file = base_dir / 'data' / 'plagenor.db'
    
    if not db_file.exists():
        log(f"SQLite database not found: {db_file}", 'ERROR')
        return False
    
    try:
        # Create compressed copy
        with open(db_file, 'rb') as f_in:
            with gzip.open(backup_file, 'wb', compresslevel=COMPRESSION_LEVEL) as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        log(f"SQLite backup created: {backup_file}", 'SUCCESS')
        return True
        
    except Exception as e:
        log(f"SQLite backup failed: {str(e)}", 'ERROR')
        return False


def backup_media_files():
    """Backup media files"""
    base_dir = Path(__file__).resolve().parent.parent
    media_dir = base_dir / 'media'
    
    if not media_dir.exists():
        log("No media directory found, skipping...", 'INFO')
        return True
    
    backup_file = BACKUP_DIR / 'media' / get_backup_filename('media', 'tar.gz')
    
    try:
        # Create tar archive of media directory
        result = subprocess.run(
            ['tar', '-czf', str(backup_file), '-C', str(media_dir.parent), 'media'],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            log(f"Media backup failed: {result.stderr}", 'ERROR')
            return False
        
        log(f"Media backup created: {backup_file}", 'SUCCESS')
        return True
        
    except Exception as e:
        log(f"Media backup failed: {str(e)}", 'ERROR')
        return False


def backup_configuration():
    """Backup configuration files"""
    base_dir = Path(__file__).resolve().parent.parent
    backup_file = BACKUP_DIR / 'logs' / get_backup_filename('config', 'json.gz')
    
    config_data = {
        'backup_date': datetime.now().isoformat(),
        'platform_version': '4.0.0',
        'database_type': get_database_type(),
        'settings': {
            'DEBUG': os.getenv('DEBUG'),
            'ALLOWED_HOSTS': os.getenv('ALLOWED_HOSTS'),
            'IBTIKAR_BUDGET_CAP': os.getenv('IBTIKAR_BUDGET_CAP'),
            'VAT_RATE': os.getenv('VAT_RATE'),
            'INVOICE_PREFIX': os.getenv('INVOICE_PREFIX'),
        }
    }
    
    try:
        with gzip.open(backup_file, 'wt') as f:
            json.dump(config_data, f, indent=2)
        
        log(f"Configuration backup created: {backup_file}", 'SUCCESS')
        return True
        
    except Exception as e:
        log(f"Configuration backup failed: {str(e)}", 'ERROR')
        return False


def cleanup_old_backups():
    """Remove backups older than retention period"""
    log(f"Cleaning up backups older than {RETENTION_DAYS} days...")
    
    cutoff_date = datetime.now() - timedelta(days=RETENTION_DAYS)
    removed_count = 0
    
    for backup_subdir in ['database', 'media', 'logs']:
        backup_path = BACKUP_DIR / backup_subdir
        
        if not backup_path.exists():
            continue
        
        for backup_file in backup_path.glob('*'):
            if backup_file.is_file():
                file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
                
                if file_time < cutoff_date:
                    backup_file.unlink()
                    removed_count += 1
                    log(f"Removed old backup: {backup_file.name}", 'INFO')
    
    log(f"Cleanup complete. Removed {removed_count} old backup(s).", 'SUCCESS')


def verify_backup(backup_file):
    """Verify backup file is valid and not corrupted"""
    if not backup_file.exists():
        return False
    
    file_size = backup_file.stat().st_size
    
    if file_size == 0:
        log(f"Backup file is empty: {backup_file}", 'ERROR')
        return False
    
    # Check if file is readable
    try:
        if backup_file.suffix == '.gz':
            with gzip.open(backup_file, 'rb') as f:
                f.read(1024)  # Read first 1KB to verify
        elif backup_file.suffix == '.c':
            with open(backup_file, 'rb') as f:
                f.read(1024)  # Read first 1KB to verify
        else:
            with open(backup_file, 'rb') as f:
                f.read(1024)
        
        log(f"Backup verified: {backup_file.name} ({file_size / 1024:.1f} KB)", 'SUCCESS')
        return True
        
    except Exception as e:
        log(f"Backup verification failed: {str(e)}", 'ERROR')
        return False


def create_backup_manifest():
    """Create a manifest file listing all backups"""
    manifest = {
        'created': datetime.now().isoformat(),
        'retention_days': RETENTION_DAYS,
        'backups': {
            'database': [],
            'media': [],
            'logs': []
        }
    }
    
    for backup_type in ['database', 'media', 'logs']:
        backup_path = BACKUP_DIR / backup_type
        if backup_path.exists():
            for f in sorted(backup_path.glob('*'), key=lambda x: x.stat().st_mtime, reverse=True):
                manifest['backups'][backup_type].append({
                    'name': f.name,
                    'size': f.stat().st_size,
                    'created': datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                })
    
    manifest_file = BACKUP_DIR / 'manifest.json'
    
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    log(f"Backup manifest created: {manifest_file}", 'SUCCESS')


def run_backup():
    """Main backup function"""
    log("=" * 60)
    log("PLAGENOR Automated Backup Starting")
    log("=" * 60)
    
    # Ensure backup directory exists
    ensure_backup_directory()
    
    # Get database type
    db_type = get_database_type()
    log(f"Detected database type: {db_type.upper()}", 'INFO')
    
    # Backup database
    db_backup_file = BACKUP_DIR / 'database' / get_backup_filename('database', 'sql.gz')
    
    if db_type == 'postgresql':
        success = backup_postgresql(db_backup_file)
    elif db_type == 'sqlite':
        success = backup_sqlite(db_backup_file)
    else:
        log(f"Unsupported database type: {db_type}", 'ERROR')
        success = False
    
    if success:
        verify_backup(db_backup_file)
    
    # Backup media files
    log("Starting media backup...", 'INFO')
    backup_media_files()
    
    # Backup configuration
    log("Starting configuration backup...", 'INFO')
    backup_configuration()
    
    # Cleanup old backups
    cleanup_old_backups()
    
    # Update manifest
    create_backup_manifest()
    
    log("=" * 60)
    log("PLAGENOR Backup Complete!")
    log("=" * 60)
    
    return success


def list_backups():
    """List all available backups"""
    if not BACKUP_DIR.exists():
        log("No backup directory found.", 'WARNING')
        return
    
    log("Available Backups:", 'INFO')
    log("-" * 40)
    
    for backup_type in ['database', 'media', 'logs']:
        backup_path = BACKUP_DIR / backup_type
        if backup_path.exists():
            files = sorted(backup_path.glob('*'), key=lambda x: x.stat().st_mtime, reverse=True)
            
            if files:
                log(f"\n{backup_type.upper()}:", 'INFO')
                for f in files:
                    size = f.stat().st_size
                    age = datetime.now() - datetime.fromtimestamp(f.stat().st_mtime)
                    
                    if size > 1024 * 1024:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    else:
                        size_str = f"{size / 1024:.1f} KB"
                    
                    log(f"  {f.name} ({size_str}, {age.days}d ago)", 'INFO')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PLAGENOR Automated Backup Script')
    parser.add_argument('--list', action='store_true', help='List available backups')
    parser.add_argument('--cleanup', action='store_true', help='Cleanup old backups only')
    args = parser.parse_args()
    
    if args.list:
        list_backups()
    elif args.cleanup:
        ensure_backup_directory()
        cleanup_old_backups()
    else:
        success = run_backup()
        sys.exit(0 if success else 1)
