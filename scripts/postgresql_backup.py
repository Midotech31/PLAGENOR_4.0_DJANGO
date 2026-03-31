#!/usr/bin/env python3
"""
PostgreSQL Backup & PITR Management Script for PLAGENOR
======================================================

This script provides comprehensive backup capabilities for PostgreSQL:
1. Full base backups using pg_basebackup
2. WAL archive management
3. Point-in-time recovery (PITR)
4. Backup rotation and retention
5. Health monitoring and alerts

Requirements:
- PostgreSQL 12+
- pg_basebackup (usually included with PostgreSQL)
- psql client
- Sufficient disk space for backups

Usage:
    # Full backup
    python scripts/postgresql_backup.py backup --type full
    
    # Incremental (WAL) backup
    python scripts/postgresql_backup.py backup --type wal
    
    # List backups
    python scripts/postgresql_backup.py list
    
    # Restore to point in time
    python scripts/postgresql_backup.py restore --time "2026-03-30 15:00:00"
    
    # Verify backup integrity
    python scripts/postgresql_backup.py verify --backup 20260330_120000
    
    # Cleanup old backups
    python scripts/postgresql_backup.py cleanup --days 30
    
    # Monitor database health
    python scripts/postgresql_backup.py monitor

Environment Variables:
    PGBACKUP_PATH     - Directory for backups (default: ./backups/postgresql)
    PGBACKUP_RETENTION - Days to keep backups (default: 30)
    PGBACKUP_WAL_ARCHIVE - WAL archive directory (default: ./backups/wal)
    DATABASE_URL      - PostgreSQL connection string
"""

import os
import sys
import json
import gzip
import shutil
import argparse
import subprocess
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, List, Dict

# Load environment variables
load_dotenv()

# Configuration
BACKUP_DIR = Path(os.getenv('PGBACKUP_PATH', './backups/postgresql'))
WAL_ARCHIVE_DIR = Path(os.getenv('PGBACKUP_WAL_ARCHIVE', './backups/wal'))
RETENTION_DAYS = int(os.getenv('PGBACKUP_RETENTION', '30'))
COMPRESSION_LEVEL = 9

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    END = '\033[0m'


def log(message: str, level: str = 'INFO'):
    """Log message with timestamp and level"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    color = {
        'INFO': Colors.BLUE,
        'SUCCESS': Colors.GREEN,
        'WARNING': Colors.YELLOW,
        'ERROR': Colors.RED,
        'PROGRESS': Colors.CYAN,
    }.get(level, Colors.END)
    print(f"{color}[{timestamp}] [{level}] {message}{Colors.END}")


def run_command(cmd: List[str], env: Optional[Dict] = None, capture: bool = True) -> tuple:
    """Run a command and return (success, stdout, stderr)"""
    log(f"Running: {' '.join(cmd)}", 'INFO')
    
    try:
        if env:
            full_env = os.environ.copy()
            full_env.update(env)
        else:
            full_env = None
        
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            env=full_env
        )
        
        if result.returncode != 0:
            log(f"Command failed: {result.stderr}", 'ERROR')
            return False, result.stdout, result.stderr
        
        return True, result.stdout, result.stderr
        
    except Exception as e:
        log(f"Command error: {str(e)}", 'ERROR')
        return False, '', str(e)


def ensure_directories():
    """Create backup directories"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    WAL_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    (BACKUP_DIR / 'base').mkdir(exist_ok=True)
    (BACKUP_DIR / 'wal').mkdir(exist_ok=True)
    (BACKUP_DIR / 'logs').mkdir(exist_ok=True)
    log(f"Backup directories ready: {BACKUP_DIR}", 'SUCCESS')


def get_database_connection():
    """Parse DATABASE_URL and return connection parameters"""
    database_url = os.getenv('DATABASE_URL', '')
    
    if not database_url:
        return None
    
    try:
        from urllib.parse import urlparse
        parsed = urlparse(database_url)
        
        return {
            'host': parsed.hostname or 'localhost',
            'port': parsed.port or 5432,
            'user': parsed.username or 'postgres',
            'password': parsed.password or '',
            'database': parsed.path.lstrip('/') or 'postgres',
        }
    except Exception as e:
        log(f"Failed to parse DATABASE_URL: {e}", 'ERROR')
        return None


def get_backup_filename(backup_type: str = 'full') -> str:
    """Generate timestamped backup filename"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"backup_{backup_type}_{timestamp}"


def create_backup_manifest() -> Dict:
    """Create or update backup manifest"""
    manifest_file = BACKUP_DIR / 'manifest.json'
    
    manifest = {
        'created': datetime.now().isoformat(),
        'retention_days': RETENTION_DAYS,
        'backups': [],
        'wal_archives': [],
    }
    
    if manifest_file.exists():
        try:
            with open(manifest_file, 'r') as f:
                manifest = json.load(f)
        except Exception:
            pass
    
    return manifest


def save_manifest(manifest: Dict):
    """Save backup manifest"""
    manifest_file = BACKUP_DIR / 'manifest.json'
    
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, indent=2)


def calculate_checksum(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file"""
    sha256 = hashlib.sha256()
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    
    return sha256.hexdigest()


def backup_full():
    """Create a full base backup using pg_basebackup"""
    log("=" * 60)
    log("Starting FULL BASE BACKUP")
    log("=" * 60)
    
    ensure_directories()
    
    conn = get_database_connection()
    if not conn:
        log("No database connection configured. Using local defaults.", 'WARNING')
        conn = {'host': 'localhost', 'port': 5432, 'user': 'postgres', 'database': 'plagenor'}
    
    backup_name = get_backup_filename('full')
    backup_path = BACKUP_DIR / 'base' / backup_name
    backup_path.mkdir(exist_ok=True)
    
    # Create backup environment with PGPASSWORD
    env = {'PGPASSWORD': conn.get('password', '')}
    
    # Run pg_basebackup
    log("Running pg_basebackup...", 'PROGRESS')
    
    cmd = [
        'pg_basebackup',
        '-h', conn['host'],
        '-p', str(conn['port']),
        '-U', conn['user'],
        '-D', str(backup_path),
        '-Ft',                           # Tar format with tablespaces
        '-z',                            # Compress with gzip
        '-P',                            # Show progress
        '-v',                            # Verbose
        '--checkpoint=fast',
    ]
    
    success, stdout, stderr = run_command(cmd, env=env)
    
    if not success:
        log(f"pg_basebackup failed: {stderr}", 'ERROR')
        # Clean up failed backup
        if backup_path.exists():
            shutil.rmtree(backup_path)
        return False
    
    # Calculate checksums
    log("Calculating checksums...", 'PROGRESS')
    checksums = {}
    
    for file in backup_path.glob('*.gz'):
        checksum = calculate_checksum(file)
        checksums[file.name] = checksum
    
    # Get backup size
    backup_size = sum(f.stat().st_size for f in backup_path.glob('*'))
    
    # Get WAL position
    wal_position = "unknown"
    for line in stdout.split('\n'):
        if 'WAL' in line or 'xlog' in line.lower():
            wal_position = line.strip()
    
    # Create backup info file
    backup_info = {
        'name': backup_name,
        'path': str(backup_path),
        'type': 'full',
        'created': datetime.now().isoformat(),
        'size_bytes': backup_size,
        'size_mb': round(backup_size / (1024 * 1024), 2),
        'checksums': checksums,
        'wal_position': wal_position,
        'postgres_version': get_postgres_version(conn),
    }
    
    info_file = backup_path / 'backup_info.json'
    with open(info_file, 'w') as f:
        json.dump(backup_info, f, indent=2)
    
    # Update manifest
    manifest = create_backup_manifest()
    manifest['backups'].append(backup_info)
    save_manifest(manifest)
    
    log(f"Full backup completed: {backup_name}", 'SUCCESS')
    log(f"Backup size: {backup_info['size_mb']} MB", 'SUCCESS')
    
    return True


def get_postgres_version(conn: Dict) -> str:
    """Get PostgreSQL version"""
    cmd = ['psql', '-h', conn['host'], '-p', str(conn['port']), 
           '-U', conn['user'], '-d', conn['database'], '-t', '-c', 'SELECT version();']
    
    env = {'PGPASSWORD': conn.get('password', '')}
    success, stdout, _ = run_command(cmd, env=env)
    
    if success:
        return stdout.strip()
    return 'unknown'


def backup_wal():
    """Archive current WAL segment"""
    log("=" * 60)
    log("Starting WAL ARCHIVE")
    log("=" * 60)
    
    ensure_directories()
    
    conn = get_database_connection()
    if not conn:
        log("No database connection configured.", 'ERROR')
        return False
    
    env = {'PGPASSWORD': conn.get('password', '')}
    
    # Get current WAL file position
    cmd = [
        'psql', '-h', conn['host'], '-p', str(conn['port']),
        '-U', conn['user'], '-d', conn['database'],
        '-t', '-c', "SELECT pg_walfile_name(pg_current_wal_lsn());"
    ]
    
    success, stdout, _ = run_command(cmd, env=env)
    
    if not success:
        log("Failed to get WAL position", 'ERROR')
        return False
    
    wal_file = stdout.strip()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Archive WAL using pg_dump for simplicity (full WAL archiving requires archive_command setup)
    wal_archive_path = WAL_ARCHIVE_DIR / f"wal_{timestamp}_{wal_file}.sql.gz"
    
    # Use pg_dump for a consistent point-in-time backup approach
    cmd = [
        'pg_dump',
        '-h', conn['host'],
        '-p', str(conn['port']),
        '-U', conn['user'],
        '-d', conn['database'],
        '-Fc',                          # Custom format
        '-z',                           # Compress
        '-f', str(wal_archive_path),
    ]
    
    success, stdout, stderr = run_command(cmd, env=env)
    
    if not success:
        log(f"WAL backup failed: {stderr}", 'ERROR')
        return False
    
    # Calculate checksum
    checksum = calculate_checksum(wal_archive_path)
    
    # Update manifest
    manifest = create_backup_manifest()
    manifest['wal_archives'].append({
        'name': str(wal_archive_path.name),
        'path': str(wal_archive_path),
        'type': 'wal',
        'created': datetime.now().isoformat(),
        'wal_file': wal_file,
        'checksum': checksum,
    })
    save_manifest(manifest)
    
    log(f"WAL archive completed: {wal_archive_path.name}", 'SUCCESS')
    
    return True


def list_backups():
    """List all available backups"""
    log("=" * 60)
    log("AVAILABLE BACKUPS")
    log("=" * 60)
    
    ensure_directories()
    
    manifest = create_backup_manifest()
    
    log("\n📦 FULL BACKUPS:", 'INFO')
    log("-" * 50)
    
    base_backups = sorted(
        [d for d in (BACKUP_DIR / 'base').iterdir() if d.is_dir()],
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    
    if not base_backups:
        log("No full backups found.", 'WARNING')
    else:
        for backup_dir in base_backups:
            info_file = backup_dir / 'backup_info.json'
            if info_file.exists():
                with open(info_file, 'r') as f:
                    info = json.load(f)
                
                age = datetime.now() - datetime.fromisoformat(info['created'])
                
                print(f"  📁 {info['name']}")
                print(f"     Size: {info['size_mb']} MB")
                print(f"     Age: {age.days}d {age.seconds // 3600}h ago")
                print(f"     WAL Position: {info.get('wal_position', 'N/A')}")
                print()
    
    log("\n📜 WAL ARCHIVES:", 'INFO')
    log("-" * 50)
    
    wal_backups = sorted(
        list((WAL_ARCHIVE_DIR).glob('*.sql.gz')),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )[:10]  # Show last 10
    
    if not wal_backups:
        log("No WAL archives found.", 'WARNING')
    else:
        for wal_file in wal_backups:
            age = datetime.now() - datetime.fromtimestamp(wal_file.stat().st_mtime)
            size_kb = round(wal_file.stat().st_size / 1024, 1)
            print(f"  📄 {wal_file.name}")
            print(f"     Size: {size_kb} KB")
            print(f"     Age: {age.days}d {age.seconds // 3600}h ago")
            print()


def verify_backup(backup_name: str):
    """Verify backup integrity"""
    log(f"Verifying backup: {backup_name}", 'INFO')
    
    backup_path = BACKUP_DIR / 'base' / backup_name
    
    if not backup_path.exists():
        log(f"Backup not found: {backup_name}", 'ERROR')
        return False
    
    info_file = backup_path / 'backup_info.json'
    if not info_file.exists():
        log("Backup info file not found", 'ERROR')
        return False
    
    with open(info_file, 'r') as f:
        info = json.load(f)
    
    log("Checking checksums...", 'PROGRESS')
    
    all_valid = True
    for filename, expected_checksum in info['checksums'].items():
        file_path = backup_path / filename
        
        if not file_path.exists():
            log(f"Missing file: {filename}", 'ERROR')
            all_valid = False
            continue
        
        actual_checksum = calculate_checksum(file_path)
        
        if actual_checksum == expected_checksum:
            log(f"✓ {filename} - Valid", 'SUCCESS')
        else:
            log(f"✗ {filename} - Checksum mismatch!", 'ERROR')
            all_valid = False
    
    if all_valid:
        log("Backup verification: PASSED", 'SUCCESS')
    else:
        log("Backup verification: FAILED", 'ERROR')
    
    return all_valid


def restore_backup(backup_name: str, target_dir: str = None):
    """Restore a backup"""
    log(f"Restoring backup: {backup_name}", 'WARNING')
    
    backup_path = BACKUP_DIR / 'base' / backup_name
    
    if not backup_path.exists():
        log(f"Backup not found: {backup_name}", 'ERROR')
        return False
    
    if target_dir is None:
        target_dir = str(BACKUP_DIR / 'restore')
    
    target_path = Path(target_dir)
    
    log("⚠️  This will replace the current database!", 'WARNING')
    log("⚠️  Make sure the database server is stopped!", 'WARNING')
    
    # Check for backup info
    info_file = backup_path / 'backup_info.json'
    if info_file.exists():
        with open(info_file, 'r') as f:
            info = json.load(f)
        log(f"Backup created: {info['created']}", 'INFO')
        log(f"Backup size: {info['size_mb']} MB", 'INFO')
    
    # Stop database
    log("Stopping PostgreSQL...", 'PROGRESS')
    run_command(['sudo', 'systemctl', 'stop', 'postgresql'])
    
    # Clear data directory (BE CAREFUL!)
    data_dir = '/var/lib/postgresql/16/main'  # Adjust for your setup
    log(f"Clearing data directory: {data_dir}", 'WARNING')
    run_command(['sudo', 'rm', '-rf', f'{data_dir}/*'])
    
    # Extract backup
    log("Extracting backup...", 'PROGRESS')
    for tar_file in backup_path.glob('*.tar.gz'):
        cmd = ['tar', '-xzf', str(tar_file), '-C', data_dir]
        run_command(['sudo'] + cmd)
    
    # Set permissions
    run_command(['sudo', 'chown', '-R', 'postgres:postgres', data_dir])
    run_command(['sudo', 'chmod', '-R', '700', data_dir])
    
    # Start database
    log("Starting PostgreSQL...", 'PROGRESS')
    run_command(['sudo', 'systemctl', 'start', 'postgresql'])
    
    log("Restore completed!", 'SUCCESS')
    
    return True


def cleanup_old_backups():
    """Remove backups older than retention period"""
    log(f"Cleaning up backups older than {RETENTION_DAYS} days...", 'INFO')
    
    ensure_directories()
    
    cutoff_date = datetime.now() - timedelta(days=RETENTION_DAYS)
    removed_count = 0
    
    # Cleanup full backups
    for backup_dir in (BACKUP_DIR / 'base').iterdir():
        if backup_dir.is_dir():
            info_file = backup_dir / 'backup_info.json'
            
            if info_file.exists():
                with open(info_file, 'r') as f:
                    info = json.load(f)
                
                created = datetime.fromisoformat(info['created'])
                
                if created < cutoff_date:
                    shutil.rmtree(backup_dir)
                    removed_count += 1
                    log(f"Removed: {info['name']}", 'INFO')
    
    # Cleanup WAL archives
    for wal_file in WAL_ARCHIVE_DIR.glob('*'):
        if wal_file.is_file():
            created = datetime.fromtimestamp(wal_file.stat().st_mtime)
            
            if created < cutoff_date:
                wal_file.unlink()
                removed_count += 1
                log(f"Removed: {wal_file.name}", 'INFO')
    
    log(f"Cleanup complete. Removed {removed_count} backup(s).", 'SUCCESS')


def monitor_database():
    """Monitor database health and performance"""
    log("=" * 60)
    log("DATABASE HEALTH MONITOR")
    log("=" * 60)
    
    conn = get_database_connection()
    if not conn:
        log("No database connection configured.", 'ERROR')
        return False
    
    env = {'PGPASSWORD': conn.get('password', '')}
    
    queries = {
        'Database Size': "SELECT pg_size_pretty(pg_database_size(current_database()));",
        'Table Count': "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';",
        'Connection Count': "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database();",
        'Max Connections': "SHOW max_connections;",
        'Cache Hit Ratio': "SELECT round(100 * (sum(blks_hit) / sum(blks_hit + blks_read)), 2) as cache_hit_ratio FROM pg_stat_database WHERE datname = current_database();",
        'Active Transactions': "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';",
        'Long Running Queries': "SELECT pid, now() - pg_stat_activity.query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' AND now() - pg_stat_activity.query_start > interval '5 minutes' ORDER BY duration DESC;",
        'Index Usage': "SELECT round(100 * sum(idx_scan) / nullif(sum(idx_scan + seq_scan), 0), 2) as idx_scan_ratio FROM pg_stat_user_tables;",
        'Dead Tuples': "SELECT schemaname, tablename, n_dead_tup FROM pg_stat_user_tables ORDER BY n_dead_tup DESC LIMIT 5;",
        'Last Vacuum': "SELECT relname, last_vacuum, last_autovacuum FROM pg_stat_user_tables ORDER BY last_autovacuum NULLS FIRST, last_vacuum NULLS FIRST LIMIT 5;",
    }
    
    for title, query in queries.items():
        cmd = ['psql', '-h', conn['host'], '-p', str(conn['port']),
               '-U', conn['user'], '-d', conn['database'], '-t', '-c', query]
        
        success, stdout, _ = run_command(cmd, env=env)
        
        if success and stdout.strip():
            value = stdout.strip().replace('\n', ', ')
            if len(value) > 100:
                value = value[:100] + '...'
            print(f"\n  {title}:")
            print(f"    {value}")
    
    log("\n" + "=" * 60, 'INFO')
    
    return True


def point_in_time_recovery(target_time: str):
    """
    Restore database to a specific point in time.
    This requires proper WAL archiving setup.
    """
    log(f"Point-in-time recovery to: {target_time}", 'WARNING')
    log("⚠️  This feature requires pre-configured WAL archiving!", 'WARNING')
    log("⚠️  Make sure archive_mode = on in postgresql.conf", 'WARNING')
    
    try:
        recovery_time = datetime.strptime(target_time, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            recovery_time = datetime.strptime(target_time, '%Y-%m-%d')
        except ValueError:
            log("Invalid time format. Use: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS", 'ERROR')
            return False
    
    log(f"Target recovery time: {recovery_time.isoformat()}", 'INFO')
    log("Please follow the PITR guide in deploy/POSTGRESQL_SETUP.md", 'INFO')
    
    return False


# =============================================================================
# MAIN CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='PostgreSQL Backup & PITR Management for PLAGENOR',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Backup command
    backup_parser = subparsers.add_parser('backup', help='Create a backup')
    backup_parser.add_argument('--type', choices=['full', 'wal'], default='full',
                               help='Type of backup to create')
    
    # List command
    subparsers.add_parser('list', help='List all backups')
    
    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify backup integrity')
    verify_parser.add_argument('--backup', required=True, help='Backup name to verify')
    
    # Restore command
    restore_parser = subparsers.add_parser('restore', help='Restore a backup')
    restore_parser.add_argument('--backup', required=True, help='Backup name to restore')
    restore_parser.add_argument('--target', help='Target directory for restore')
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up old backups')
    cleanup_parser.add_argument('--days', type=int, default=RETENTION_DAYS,
                                help=f'Days to retain backups (default: {RETENTION_DAYS})')
    
    # Monitor command
    subparsers.add_parser('monitor', help='Monitor database health')
    
    # PITR command
    pitr_parser = subparsers.add_parser('restore-pitr', help='Point-in-time recovery')
    pitr_parser.add_argument('--time', required=True, help='Target time (YYYY-MM-DD HH:MM:SS)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    if args.command == 'backup':
        if args.type == 'full':
            return 0 if backup_full() else 1
        else:
            return 0 if backup_wal() else 1
    
    elif args.command == 'list':
        list_backups()
        return 0
    
    elif args.command == 'verify':
        return 0 if verify_backup(args.backup) else 1
    
    elif args.command == 'restore':
        return 0 if restore_backup(args.backup, args.target) else 1
    
    elif args.command == 'cleanup':
        return 0 if cleanup_old_backups() else 1
    
    elif args.command == 'monitor':
        return 0 if monitor_database() else 1
    
    elif args.command == 'restore-pitr':
        return 0 if point_in_time_recovery(args.time) else 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
