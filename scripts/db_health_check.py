#!/usr/bin/env python3
"""
PLAGENOR Database Health Check & Stability Analysis
===================================================

This script performs a comprehensive analysis of the PLAGENOR database
to assess application stability, identify performance bottlenecks,
and recommend optimizations.

Usage:
    python scripts/db_health_check.py --verbose
    python scripts/db_health_check.py --fix  # Apply recommendations
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')

import django
django.setup()

from django.db import connection
from django.apps import apps
from django.conf import settings

# Colors
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
CYAN = '\033[96m'
END = '\033[0m'


def log(msg, level='INFO'):
    color = {'INFO': BLUE, 'OK': GREEN, 'WARN': YELLOW, 'ERROR': RED, 'HEADER': CYAN}.get(level, END)
    print(f"{color}[{datetime.now().strftime('%H:%M:%S')}] {msg}{END}")


def check_database_connection():
    """Check if database connection works"""
    log("Checking database connection...", 'HEADER')
    
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            log(f"✓ Database connected: {version[:50]}...", 'OK')
            return True
    except Exception as e:
        log(f"✗ Database connection failed: {e}", 'ERROR')
        return False


def check_model_indexes():
    """Analyze model indexes"""
    log("Analyzing model indexes...", 'HEADER')
    
    missing_indexes = []
    models_checked = 0
    
    # Check core models
    from core.models import Request, Service, Invoice
    from accounts.models import User, MemberProfile
    from notifications.models import Notification
    from documents.models import Document
    
    # Critical models that need indexes
    critical_lookups = [
        (Request, ['requester', 'status', 'channel', 'assigned_to', 'created_at', 'display_id']),
        (User, ['username', 'email', 'ibtikar_id', 'role']),
        (MemberProfile, ['user', 'available', 'productivity_status']),
        (Invoice, ['client', 'request', 'payment_status', 'invoice_number']),
        (Notification, ['user', 'notification_type', 'created_at', 'read']),
    ]
    
    for model, expected_indexes in critical_lookups:
        models_checked += 1
        table_name = model._meta.db_table
        
        # Check existing indexes
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT indexname, indexdef 
                FROM pg_indexes 
                WHERE tablename = %s
            """, [table_name])
            existing_indexes = {row[0] for row in cursor.fetchall()}
        
        # Check for missing indexes on foreign keys and frequently queried fields
        for field_name in expected_indexes:
            try:
                field = model._meta.get_field(field_name)
                index_name = f"{table_name}_{field_name}_idx"
                
                has_index = any(
                    field_name in idx or index_name in idx
                    for idx in existing_indexes
                )
                
                if not has_index and not field.primary_key:
                    missing_indexes.append((model, field_name, table_name))
                    log(f"  ⚠ Missing index on {table_name}.{field_name}", 'WARN')
                else:
                    log(f"  ✓ {table_name}.{field_name} has index", 'OK')
            except Exception:
                pass
    
    return missing_indexes


def check_json_field_usage():
    """Analyze JSONField usage for potential optimization"""
    log("Analyzing JSONField usage...", 'HEADER')
    
    json_fields = []
    
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if hasattr(field, 'db_type') and field.db_type(connection) == 'jsonb':
                json_fields.append((model._meta.db_table, field.name))
                log(f"  JSON field: {model._meta.db_table}.{field.name}", 'INFO')
    
    if json_fields:
        log(f"Found {len(json_fields)} JSON fields - ensure proper indexing if queried", 'WARN')
    
    return json_fields


def check_query_performance():
    """Check for potential N+1 query issues"""
    log("Checking for N+1 query patterns...", 'HEADER')
    
    # Analyze views for common N+1 patterns
    from django.db.models import QuerySet
    
    # Check select_related usage
    n_plus_one_risks = []
    
    # Check Request queries
    with connection.cursor() as cursor:
        # Check if foreign keys are properly indexed
        cursor.execute("""
            SELECT 
                tc.table_name, 
                kcu.column_name,
                tc.constraint_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_name IN ('requests', 'invoices', 'notifications', 'messages')
            ORDER BY tc.table_name;
        """)
        
        foreign_keys = cursor.fetchall()
        log(f"Found {len(foreign_keys)} foreign key constraints", 'INFO')
        
        # Check for missing indexes on foreign keys
        cursor.execute("""
            SELECT 
                t.relname AS table_name,
                a.attname AS column_name
            FROM pg_class t
            JOIN pg_index i ON t.oid = i.indrelid
            JOIN pg_class t2 ON i.indexrelid = t2.oid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey)
            WHERE i.indisunique = false
                AND i.indisprimary = false
                AND t.relname IN ('requests', 'invoices', 'notifications', 'messages')
            ORDER BY t.relname;
        """)
        
        indexed_columns = set(cursor.fetchall())
        
        for fk_table, fk_column, _ in foreign_keys:
            if (fk_table, fk_column) not in indexed_columns:
                n_plus_one_risks.append((fk_table, fk_column))
                log(f"  ⚠ FK without index: {fk_table}.{fk_column}", 'WARN')
    
    return n_plus_one_risks


def check_database_size():
    """Check database and table sizes"""
    log("Analyzing database size...", 'HEADER')
    
    with connection.cursor() as cursor:
        # Database size
        cursor.execute("""
            SELECT pg_size_pretty(pg_database_size(current_database()));
        """)
        db_size = cursor.fetchone()[0]
        log(f"Database size: {db_size}", 'INFO')
        
        # Table sizes
        cursor.execute("""
            SELECT 
                schemaname,
                relname AS table_name,
                pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
                n_live_tup AS live_rows,
                n_dead_tup AS dead_rows
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(relid) DESC
            LIMIT 10;
        """)
        
        log("\nTop 10 largest tables:", 'HEADER')
        for row in cursor.fetchall():
            log(f"  {row[1]}: {row[2]} ({row[3]} rows, {row[4]} dead)", 'INFO')
        
        # Check for bloat
        cursor.execute("""
            SELECT 
                schemaname,
                relname AS table_name,
                pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS bloat_size
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
              AND pg_total_relation_size(relid) - pg_relation_size(relid) > 10 * 1024 * 1024
            ORDER BY pg_total_relation_size(relid) - pg_relation_size(relid) DESC;
        """)
        
        bloat = cursor.fetchall()
        if bloat:
            log("\nTables with significant bloat (>10MB):", 'WARN')
            for row in bloat:
                log(f"  {row[1]}: {row[2]} bloat", 'WARN')
        
        return db_size


def check_cache_performance():
    """Check query cache hit ratio"""
    log("Checking cache performance...", 'HEADER')
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                sum(blks_hit) * 100.0 / nullif(sum(blks_hit) + sum(blks_read), 0) AS cache_hit_ratio,
                sum(blks_hit) AS hits,
                sum(blks_read) AS reads
            FROM pg_stat_database
            WHERE datname = current_database();
        """)
        
        result = cursor.fetchone()
        if result and result[0]:
            ratio = round(result[0], 2)
            hits = result[1] or 0
            reads = result[2] or 0
            
            log(f"Cache hit ratio: {ratio}%", 'INFO' if ratio > 90 else 'WARN')
            log(f"Cache hits: {hits:,} | Reads: {reads:,}", 'INFO')
            
            if ratio < 90:
                log("⚠ Cache hit ratio is below 90% - consider increasing shared_buffers", 'WARN')
            
            return ratio
        return 0


def check_connection_usage():
    """Check current connection usage"""
    log("Checking connection usage...", 'HEADER')
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                current_setting('max_connections')::int AS max_conn,
                COUNT(*) AS current_conn,
                COUNT(*) FILTER (WHERE state = 'active') AS active_conn,
                COUNT(*) FILTER (WHERE state = 'idle') AS idle_conn
            FROM pg_stat_activity
            WHERE datname = current_database();
        """)
        
        result = cursor.fetchone()
        if result:
            max_conn = result[0]
            current = result[1]
            active = result[2]
            idle = result[3]
            usage_pct = round(100 * current / max_conn, 1)
            
            log(f"Connections: {current}/{max_conn} ({usage_pct}%)", 
                'OK' if usage_pct < 50 else 'WARN')
            log(f"  Active: {active} | Idle: {idle}", 'INFO')
            
            if usage_pct > 80:
                log("⚠ Connection usage high - consider PgBouncer", 'WARN')
            
            return usage_pct
        return 0


def check_long_running_queries():
    """Check for long-running queries"""
    log("Checking for long-running queries...", 'HEADER')
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                pid,
                now() - query_start AS duration,
                state,
                LEFT(query, 100) AS query_preview
            FROM pg_stat_activity
            WHERE state = 'active'
              AND now() - query_start > interval '5 seconds'
            ORDER BY duration DESC
            LIMIT 5;
        """)
        
        long_queries = cursor.fetchall()
        
        if long_queries:
            log(f"Found {len(long_queries)} long-running queries:", 'WARN')
            for row in long_queries:
                log(f"  PID {row[0]}: {row[1]} - {row[3]}...", 'WARN')
        else:
            log("No long-running queries found", 'OK')
        
        return len(long_queries)


def check_vacuum_status():
    """Check vacuum/autovacuum status"""
    log("Checking vacuum status...", 'HEADER')
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                relname AS table_name,
                last_vacuum,
                last_autovacuum,
                n_live_tup,
                n_dead_tup,
                CASE 
                    WHEN n_dead_tup > 10000 THEN 'CRITICAL'
                    WHEN n_dead_tup > 1000 THEN 'WARNING'
                    ELSE 'OK'
                END AS status
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
              AND n_dead_tup > 0
            ORDER BY n_dead_tup DESC
            LIMIT 5;
        """)
        
        vacuum_issues = cursor.fetchall()
        
        if vacuum_issues:
            log("Tables needing vacuum:", 'WARN')
            for row in vacuum_issues:
                status_icon = '🔴' if row[5] == 'CRITICAL' else '🟡'
                log(f"  {status_icon} {row[0]}: {row[4]} dead tuples (last vacuum: {row[1]}, autovacuum: {row[2]})", row[5])
        else:
            log("All tables vacuumed properly", 'OK')
        
        return vacuum_issues


def generate_recommendations(missing_indexes, n_plus_one_risks, cache_ratio, connection_usage):
    """Generate optimization recommendations"""
    log("\n" + "=" * 60, 'HEADER')
    log("RECOMMENDATIONS", 'HEADER')
    log("=" * 60, 'HEADER')
    
    recommendations = []
    
    if missing_indexes:
        recommendations.append("\n📊 Missing Indexes (add for better performance):")
        for model, field, table in missing_indexes[:5]:
            recommendations.append(f"  CREATE INDEX idx_{table}_{field} ON {table} ({field});")
    
    if n_plus_one_risks:
        recommendations.append("\n⚡ N+1 Query Risks:")
        for table, column in n_plus_one_risks[:5]:
            recommendations.append(f"  Add index on {table}.{column} for foreign key lookups")
    
    if cache_ratio < 90:
        recommendations.append(f"\n💾 Low Cache Hit Ratio ({cache_ratio}%):")
        recommendations.append("  - Increase shared_buffers to 25% of RAM")
        recommendations.append("  - Ensure effective_cache_size is set to 75% of RAM")
    
    if connection_usage > 50:
        recommendations.append("\n🔌 High Connection Usage:")
        recommendations.append("  - Use PgBouncer for connection pooling")
        recommendations.append("  - Set CONN_MAX_AGE=600 in Django settings")
    
    recommendations.append("\n✅ Recommended Migrations:")
    recommendations.append("  python manage.py migrate")
    recommendations.append("\n✅ Regular Maintenance:")
    recommendations.append("  VACUUM ANALYZE (runs automatically with autovacuum)")
    recommendations.append("  python scripts/db_health_check.py --fix")
    
    for rec in recommendations:
        log(rec, 'INFO')
    
    return recommendations


def main():
    log("=" * 60, 'HEADER')
    log("PLAGENOR Database Health Check", 'HEADER')
    log("=" * 60, 'HEADER')
    
    # Run all checks
    checks = {
        'Connection': check_database_connection(),
        'Indexes': check_model_indexes(),
        'JSON Fields': check_json_field_usage(),
        'Query Performance': check_query_performance(),
        'Database Size': check_database_size(),
        'Cache Performance': check_cache_performance(),
        'Connection Usage': check_connection_usage(),
        'Long Queries': check_long_running_queries(),
        'Vacuum Status': check_vacuum_status(),
    }
    
    # Summary
    log("\n" + "=" * 60, 'HEADER')
    log("SUMMARY", 'HEADER')
    log("=" * 60, 'HEADER')
    
    total_issues = 0
    for name, result in checks.items():
        if isinstance(result, list):
            total_issues += len(result)
    
    if total_issues == 0:
        log("✅ Database health: EXCELLENT", 'OK')
    elif total_issues < 5:
        log(f"🟡 Database health: GOOD ({total_issues} minor issues)", 'WARN')
    else:
        log(f"🔴 Database health: NEEDS ATTENTION ({total_issues} issues)", 'ERROR')
    
    log(f"\nTimestamp: {datetime.now().isoformat()}", 'INFO')
    
    # Generate recommendations
    missing_indexes = checks.get('Indexes', [])
    n_plus_one_risks = checks.get('Query Performance', [])
    cache_ratio = checks.get('Cache Performance', 100)
    connection_usage = checks.get('Connection Usage', 0)
    
    generate_recommendations(missing_indexes, n_plus_one_risks, cache_ratio, connection_usage)
    
    return 0 if total_issues < 5 else 1


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='PLAGENOR Database Health Check')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--fix', action='store_true', help='Apply fixes')
    args = parser.parse_args()
    
    sys.exit(main())
