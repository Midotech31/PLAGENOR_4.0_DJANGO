# PostgreSQL Setup Guide for PLAGENOR
## Complete Production-Ready Database Configuration

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Connection Pooling with PgBouncer](#connection-pooling-with-pgbouncer)
5. [Backup Strategy](#backup-strategy)
6. [WAL Archiving & PITR](#wal-archiving--pitr)
7. [Monitoring](#monitoring)
8. [Performance Tuning](#performance-tuning)
9. [Security](#security)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 2 GB | 8 GB |
| Disk | 20 GB | 100 GB+ (SSD) |
| OS | Ubuntu 22.04 / Debian 12 | Ubuntu 22.04 LTS |

### Required Packages

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y postgresql-16 postgresql-client-16
sudo apt install -y pgbouncer
sudo apt install -y python3-psycopg2 python3-pip
```

---

## Installation

### 1. Install PostgreSQL 16

```bash
# Add PostgreSQL repository
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
sudo apt update

# Install PostgreSQL 16
sudo apt install -y postgresql-16 postgresql-client-16

# Start and enable PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 2. Install PgBouncer

```bash
sudo apt install -y pgbouncer
```

---

## Configuration

### 1. Copy PostgreSQL Configuration

```bash
# Backup original configuration
sudo cp /etc/postgresql/16/main/postgresql.conf /etc/postgresql/16/main/postgresql.conf.backup
sudo cp /etc/postgresql/16/main/pg_hba.conf /etc/postgresql/16/main/pg_hba.conf.backup

# Copy production configuration
sudo cp deploy/postgresql/postgresql.conf /etc/postgresql/16/main/postgresql.conf

# Set permissions
sudo chown postgres:postgres /etc/postgresql/16/main/postgresql.conf
sudo chmod 640 /etc/postgresql/16/main/postgresql.conf
```

### 2. Configure pg_hba.conf

```bash
sudo nano /etc/postgresql/16/main/pg_hba.conf
```

Add these lines:

```conf
# PLAGENOR - Local connections
local   all             postgres                                peer
local   all             all                                     peer

# PLAGENOR - IPv4 local connections (for PgBouncer)
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             ::1/128                 scram-sha-256

# PLAGENOR - Remote connections (restrict to your network)
host    all             plagenor        10.0.0.0/8              scram-sha-256
host    all             plagenor        192.168.0.0/16          scram-sha-256
```

### 3. Create Database and User

```bash
# Switch to postgres user
sudo -u postgres psql

# Create database
CREATE DATABASE plagenor;

# Create application user
CREATE USER plagenor WITH LOGIN PASSWORD 'your_secure_password';

# Grant privileges
GRANT ALL PRIVILEGES ON DATABASE plagenor TO plagenor;

# Grant schema privileges
\c plagenor
GRANT ALL ON SCHEMA public TO plagenor;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO plagenor;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO plagenor;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO plagenor;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO plagenor;

# Exit
\q
```

### 4. Configure PgBouncer

```bash
# Copy PgBouncer configuration
sudo cp deploy/postgresql/pgbouncer.ini /etc/pgbouncer/pgbouncer.ini
sudo chown pgbouncer:pgbouncer /etc/pgbouncer/pgbouncer.ini
sudo chmod 640 /etc/pgbouncer/pgbouncer.ini

# Create auth file
sudo nano /etc/pgbouncer/userlist.txt
```

Add users:
```
"postgres" "your_postgres_password"
"plagenor" "your_plagenor_password"
```

```bash
# Set permissions
sudo chown pgbouncer:pgbouncer /etc/pgbouncer/userlist.txt
sudo chmod 640 /etc/pgbouncer/userlist.txt
```

### 5. Update Django Settings

Edit your `.env` file:

```bash
# For PgBouncer (recommended)
DATABASE_URL=postgresql://plagenor:your_plagenor_password@127.0.0.1:6432/plagenor

# Or direct connection (for development only)
DATABASE_URL=postgresql://plagenor:your_plagenor_password@127.0.0.1:5432/plagenor
```

Update [`plagenor/settings.py`](plagenor/settings.py):

```python
# Connection pooling settings
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'plagenor',
        'USER': 'plagenor',
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': '127.0.0.1',
        'PORT': 6432,  # PgBouncer port
        'CONN_MAX_AGE': 600,  # Connection reuse
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}
```

### 6. Enable and Start Services

```bash
# Reload PostgreSQL
sudo systemctl reload postgresql

# Enable and start PgBouncer
sudo systemctl enable pgbouncer
sudo systemctl start pgbouncer

# Check status
sudo systemctl status postgresql
sudo systemctl status pgbouncer
```

---

## Connection Pooling with PgBouncer

### Why PgBouncer?

PgBouncer provides connection pooling which is essential for Django applications:

- **Django opens multiple connections per request** (admin, ORM, views)
- **PostgreSQL has a connection limit** (default: 100)
- **PgBouncer reuses connections**, reducing overhead
- **Prevents "too many connections" errors**

### Pool Modes

| Mode | Description | Best For |
|------|-------------|----------|
| Session | One connection per client | Legacy apps |
| Transaction | Connections per transaction | Django (RECOMMENDED) |
| Statement | Connections per statement | High-frequency queries |

### PgBouncer Management

```bash
# Connect to PgBouncer admin console
psql -h 127.0.0.1 -p 6432 -U postgres -d pgbouncer

# Useful commands:
SHOW LISTS;
SHOW POOLS;
SHOW CLIENTS;
SHOW SERVERS;
SHOW VERSION;
```

---

## Backup Strategy

### Automated Full Backup (Daily)

Add to crontab:

```bash
# Daily full backup at 2 AM
0 2 * * * /opt/plagenor/venv/bin/python /opt/plagenor/scripts/postgresql_backup.py backup --type full

# Hourly WAL backup
0 * * * * /opt/plagenor/venv/bin/python /opt/plagenor/scripts/postgresql_backup.py backup --type wal

# Cleanup old backups (weekly)
0 3 * * 0 /opt/plagenor/venv/bin/python /opt/plagenor/scripts/postgresql_backup.py cleanup --days 30
```

### Manual Backup Commands

```bash
# Full backup
python scripts/postgresql_backup.py backup --type full

# WAL archive
python scripts/postgresql_backup.py backup --type wal

# List backups
python scripts/postgresql_backup.py list

# Verify backup
python scripts/postgresql_backup.py verify --backup backup_full_20260330_120000

# Cleanup
python scripts/postgresql_backup.py cleanup --days 30
```

### Restore from Backup

```bash
# List available backups
python scripts/postgresql_backup.py list

# Restore specific backup
sudo systemctl stop plagenor
sudo systemctl stop postgresql
python scripts/postgresql_backup.py restore --backup backup_full_20260330_120000
sudo systemctl start postgresql
```

---

## WAL Archiving & PITR

### Understanding WAL

Write-Ahead Logging (WAL) is PostgreSQL's mechanism for:
- Data durability
- Point-in-time recovery
- Replication

### Enable WAL Archiving

1. **Update postgresql.conf**:

```bash
sudo nano /etc/postgresql/16/main/postgresql.conf
```

Set these parameters:

```conf
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /var/backups/postgresql/wal/%f && cp %p /var/backups/postgresql/wal/%f'
archive_timeout = 300
```

2. **Create WAL archive directory**:

```bash
sudo mkdir -p /var/backups/postgresql/wal
sudo chown postgres:postgres /var/backups/postgresql/wal
sudo chmod 700 /var/backups/postgresql/wal
```

3. **Reload PostgreSQL**:

```bash
sudo systemctl reload postgresql
```

### Point-in-Time Recovery (PITR)

PITR allows restoring to any point in time, not just the last backup.

#### Step 1: Identify Recovery Target

```bash
# Check your backups
python scripts/postgresql_backup.py list
```

#### Step 2: Prepare Recovery Environment

```bash
# Stop PostgreSQL
sudo systemctl stop postgresql

# Create recovery directory
sudo mkdir -p /var/lib/postgresql/16/recovery
sudo chown postgres:postgres /var/lib/postgresql/16/recovery
```

#### Step 3: Restore Base Backup

```bash
# Extract your latest base backup to recovery directory
# (This is done automatically by the restore command)
```

#### Step 4: Create Recovery Configuration

```bash
sudo nano /etc/postgresql/16/main/recovery.conf
```

Add:

```conf
# Point-in-time recovery configuration
restore_command = 'cp /var/backups/postgresql/wal/%f %p'
recovery_target_time = '2026-03-30 15:00:00 Africa/Algiers'
recovery_target_action = 'promote'

# Or target a named restore point
# recovery_target_name = 'before_dangerous_operation'
```

#### Step 5: Start Recovery

```bash
sudo systemctl start postgresql

# Monitor recovery
sudo tail -f /var/log/postgresql/postgresql-16-main.log
```

### Continuous Archiving (Recommended)

For production, use `pgBackRest` or `Barman` for professional backup management:

```bash
# Install pgBackRest
sudo apt install pgbackrest

# Configure pgBackRest
sudo nano /etc/pgbackrest.conf
```

Example configuration:

```ini
[plagenor]
db-path=/var/lib/postgresql/16/main
db1-host=localhost
db1-port=5432
db1-path=/var/lib/postgresql/16/main

[global]
repo1-path=/var/backups/pgbackrest
repo1-retention-full=7
repo1-retention-diff=3
repo1-retention-archive=30
process-max=2
log-level-console=info
log-level-file=debug

[global:archive-push]
compress-level=3
```

---

## Monitoring

### Database Health Monitoring

```bash
# Run built-in monitor
python scripts/postgresql_backup.py monitor
```

### Key Metrics to Track

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| Cache Hit Ratio | > 95% | 90-95% | < 90% |
| Connection Usage | < 50% | 50-80% | > 80% |
| Long Queries | 0 | 1-5 | > 5 |
| Dead Tuples | < 1000 | 1000-10000 | > 10000 |
| Replication Lag | < 1s | 1-10s | > 10s |

### Useful SQL Queries

```sql
-- Check database size
SELECT pg_size_pretty(pg_database_size('plagenor'));

-- Check table sizes
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 10;

-- Check slow queries
SELECT query, calls, mean_time, total_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- Check index usage
SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC
LIMIT 10;

-- Check bloat
SELECT tablename, pg_size_pretty(pg_total_relation_size(tablename::regclass)),
       pg_size_pretty(pg_relation_size(tablename::regclass))
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(tablename::regclass) DESC;
```

### Integration with Monitoring Systems

#### Prometheus Exporter

```bash
# Install postgres_exporter
sudo apt install prometheus-postgres-exporter
```

Configure:

```bash
sudo nano /etc/default/prometheus-postgres-exporter
```

```
DATA_SOURCE_NAME="postgresql://plagenor:password@localhost:5432/plagenor?sslmode=disable"
```

---

## Performance Tuning

### Quick Performance Checklist

- [ ] `shared_buffers` = 25% of RAM
- [ ] `effective_cache_size` = 75% of RAM
- [ ] `work_mem` = 10-50MB
- [ ] `maintenance_work_mem` = 256MB+
- [ ] `max_connections` = 100 (with PgBouncer)
- [ ] Indexes on foreign keys
- [ ] Regular `VACUUM` and `ANALYZE`

### Index Recommendations

Based on PLAGENOR's Django models:

```sql
-- Add these indexes for better performance

-- For core.Request model
CREATE INDEX CONCURRENTLY idx_request_status ON core_request (status);
CREATE INDEX CONCURRENTLY idx_request_created ON core_request (created_at);
CREATE INDEX CONCURRENTLY idx_request_assignee ON core_request (assigned_to_id);

-- For core.Quote model
CREATE INDEX CONCURRENTLY idx_quote_client ON core_quote (client_id);
CREATE INDEX CONCURRENTLY idx_quote_status ON core_quote (status);

-- For core.Invoice model
CREATE INDEX CONCURRENTLY idx_invoice_client ON core_invoice (client_id);
CREATE INDEX CONCURRENTLY idx_invoice_status ON core_invoice (payment_status);

-- For accounts.User model
CREATE INDEX CONCURRENTLY idx_user_department ON accounts_user (department_id);
CREATE INDEX CONCURRENTLY idx_user_username ON accounts_user (username);
```

### Vacuum Configuration

```sql
-- Enable autovacuum tuning
ALTER SYSTEM SET autovacuum_max_workers = 3;
ALTER SYSTEM SET autovacuum_naptime = '1min';
ALTER SYSTEM SET autovacuum_vacuum_threshold = 50;
ALTER SYSTEM SET autovacuum_analyze_threshold = 50;
ALTER SYSTEM SET autovacuum_vacuum_scale_factor = 0.1;
ALTER SYSTEM SET autovacuum_analyze_scale_factor = 0.05;

-- Reload configuration
SELECT pg_reload_conf();
```

---

## Security

### Secure Configuration Checklist

- [ ] Use `scram-sha-256` authentication
- [ ] Restrict `pg_hba.conf` to trusted IPs
- [ ] Enable SSL for connections
- [ ] Use strong passwords
- [ ] Regular security updates
- [ ] Enable logging of suspicious activities
- [ ] Use PgBouncer to limit connections
- [ ] Regular backups

### Enable SSL

```bash
# Generate SSL certificates
sudo openssl req -new -x509 -days 365 -nodes \
    -out /etc/postgresql/16/main/server.crt \
    -keyout /etc/postgresql/16/main/server.key

sudo chown postgres:postgres /etc/postgresql/16/main/server.*
sudo chmod 600 /etc/postgresql/16/main/server.key

# Update postgresql.conf
sudo nano /etc/postgresql/16/main/postgresql.conf
```

Add:

```conf
ssl = on
ssl_cert_file = '/etc/postgresql/16/main/server.crt'
ssl_key_file = '/etc/postgresql/16/main/server.key'
```

```bash
sudo systemctl reload postgresql
```

---

## Troubleshooting

### Common Issues

#### 1. "Too many connections"

```bash
# Check current connections
psql -h 127.0.0.1 -p 5432 -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Check PgBouncer
psql -h 127.0.0.1 -p 6432 -U postgres -d pgbouncer -c "SHOW POOLS;"

# Increase PgBouncer pool size if needed
sudo nano /etc/pgbouncer/pgbouncer.ini
# Adjust: default_pool_size = 30
sudo systemctl reload pgbouncer
```

#### 2. "Permission denied"

```bash
# Fix ownership
sudo chown -R postgres:postgres /var/lib/postgresql/16/main
sudo chmod -R 700 /var/lib/postgresql/16/main

# Fix database permissions
sudo -u postgres psql -d plagenor -c "GRANT ALL ON SCHEMA public TO plagenor;"
```

#### 3. PgBouncer connection refused

```bash
# Check if PgBouncer is running
sudo systemctl status pgbouncer

# Check logs
sudo journalctl -u pgbouncer -n 50

# Test connection
psql -h 127.0.0.1 -p 6432 -U postgres -d pgbouncer
```

#### 4. Backup failed

```bash
# Check disk space
df -h

# Check PostgreSQL is running
sudo systemctl status postgresql

# Check permissions
ls -la /var/backups/postgresql/

# Manually run backup with verbose output
python scripts/postgresql_backup.py backup --type full
```

#### 5. Slow queries

```sql
-- Find slow queries
SELECT query, calls, mean_time, total_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- Enable auto_explain for query plans
ALTER SYSTEM SET auto_explain.log_min_duration = '5s';
ALTER SYSTEM SET auto_explain.log_analyze = on;
SELECT pg_reload_conf();
```

### Emergency Recovery

If the database is corrupted:

```bash
# 1. Stop all services
sudo systemctl stop plagenor
sudo systemctl stop gunicorn
sudo systemctl stop pgbouncer
sudo systemctl stop postgresql

# 2. Backup corrupted data directory
sudo cp -r /var/lib/postgresql/16/main /var/lib/postgresql/16/main.corrupted

# 3. Restore from last good backup
python scripts/postgresql_backup.py restore --backup backup_full_20260330_020000

# 4. Start services
sudo systemctl start postgresql
sudo systemctl start pgbouncer
sudo systemctl start gunicorn
sudo systemctl start plagenor
```

---

## Support

For issues with PostgreSQL configuration:
- Documentation: https://www.postgresql.org/docs/16/
- PgBouncer: https://www.pgbouncer.org/
- PLAGENOR Issues: https://github.com/your-repo/plagenor

---

**Last Updated**: 2026-03-30
**Version**: 4.0.0
