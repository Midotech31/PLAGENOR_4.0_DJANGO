-- =============================================================================
-- PostgreSQL Monitoring Queries for PLAGENOR
-- =============================================================================
-- Use these queries to monitor database health and performance.
-- 
-- Usage:
--   psql -h localhost -U postgres -d plagenor -f scripts/db_monitor_queries.sql
--   Or run individual queries as needed.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- SECTION 1: DATABASE OVERVIEW
-- -----------------------------------------------------------------------------

-- Database size
SELECT 
    datname AS database_name,
    pg_size_pretty(pg_database_size(datname)) AS size,
    pg_database_size(datname) AS size_bytes
FROM pg_database
WHERE datname = current_database()
ORDER BY pg_database_size(datname) DESC;

-- -----------------------------------------------------------------------------
-- SECTION 2: CONNECTION MONITORING
-- -----------------------------------------------------------------------------

-- Current connections
SELECT 
    state,
    COUNT(*) AS count,
    ARRAY_AGG(DISTINCT usename) AS users
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state;

-- Connection details
SELECT 
    pid,
    usename AS username,
    application_name,
    client_addr,
    backend_start,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY backend_start DESC;

-- Maximum connections used vs allowed
SELECT 
    current_setting('max_connections')::int AS max_connections,
    COUNT(*) AS current_connections,
    ROUND(100.0 * COUNT(*) / current_setting('max_connections')::int, 2) AS usage_percent
FROM pg_stat_activity;

-- -----------------------------------------------------------------------------
-- SECTION 3: CACHE & PERFORMANCE
-- -----------------------------------------------------------------------------

-- Cache hit ratio (should be > 95%)
SELECT 
    datname,
    round(100 * (sum(blks_hit) / nullif(sum(blks_hit + blks_read), 0)), 2) AS cache_hit_ratio,
    sum(blks_hit) AS hits,
    sum(blks_read) AS reads
FROM pg_stat_database
WHERE datname = current_database()
GROUP BY datname;

-- Database statistics
SELECT 
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    conflicts
FROM pg_stat_database
WHERE datname = current_database();

-- -----------------------------------------------------------------------------
-- SECTION 4: TABLE ANALYSIS
-- -----------------------------------------------------------------------------

-- Table sizes (top 20)
SELECT 
    schemaname,
    relname AS table_name,
    n_tup_ins AS inserts,
    n_tup_upd AS updates,
    n_tup_del AS deletes,
    n_live_tup AS live_rows,
    n_dead_tup AS dead_rows,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS table_size
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 20;

-- Tables with high bloat
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(tablename::regclass)) AS total_size,
    pg_size_pretty(pg_relation_size(tablename::regclass)) AS table_size,
    pg_size_pretty(pg_total_relation_size(tablename::regclass) - pg_relation_size(tablename::regclass)) AS bloat_size,
    ROUND(100 * (pg_total_relation_size(tablename::regclass) - pg_relation_size(tablename::regclass)) 
          / NULLIF(pg_relation_size(tablename::regclass), 0), 2) AS bloat_percent
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(tablename::regclass) - pg_relation_size(tablename::regclass) DESC
LIMIT 10;

-- Tables needing vacuum
SELECT 
    schemaname,
    relname AS table_name,
    n_dead_tup AS dead_tuples,
    n_live_tup AS live_tuples,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY n_dead_tup DESC
LIMIT 10;

-- Tables with missing indexes (high seq_scan vs idx_scan)
SELECT 
    schemaname,
    relname AS table_name,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    ROUND(100.0 * idx_scan / NULLIF(idx_scan + seq_scan, 0), 2) AS index_usage_percent
FROM pg_stat_user_tables
WHERE schemaname = 'public'
  AND (idx_scan + seq_scan) > 1000
ORDER BY (idx_scan + seq_scan) DESC
LIMIT 10;

-- -----------------------------------------------------------------------------
-- SECTION 5: INDEX ANALYSIS
-- -----------------------------------------------------------------------------

-- Index usage (top 20)
SELECT 
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan AS scans,
    idx_tup_read AS tuples_read,
    idx_tup_fetch AS tuples_fetched,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC
LIMIT 20;

-- Unused indexes (can be dropped)
SELECT 
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    pg_relation_size(indexrelid) AS index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;

-- Index bloat
SELECT 
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    pg_size_pretty(pg_relation_size(indexrelid) * (n_dead_tup::float / NULLIF(n_live_tup + n_dead_tup, 0))) AS estimated_bloat
FROM pg_stat_user_indexes ui
JOIN pg_stat_user_tables ut ON ui.relid = ut.relid
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;

-- -----------------------------------------------------------------------------
-- SECTION 6: QUERY PERFORMANCE
-- -----------------------------------------------------------------------------

-- Long running queries
SELECT 
    pid,
    now() - query_start AS duration,
    state,
    LEFT(query, 200) AS query_preview,
    waiting
FROM pg_stat_activity
WHERE state != 'idle'
  AND now() - query_start > interval '5 minutes'
ORDER BY duration DESC;

-- Queries by total time (requires pg_stat_statements extension)
-- Enable: CREATE EXTENSION pg_stat_statements;
SELECT 
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

-- Queries by mean time
SELECT 
    query,
    calls,
    mean_exec_time,
    min_exec_time,
    max_exec_time,
    stddev_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 20;

-- -----------------------------------------------------------------------------
-- SECTION 7: REPLICATION & WAL
-- -----------------------------------------------------------------------------

-- WAL activity (if replication is enabled)
SELECT 
    pg_current_wal_lsn() AS current_lsn,
    pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0') AS bytes_in_wal,
    pg_walfile_name(pg_current_wal_lsn()) AS current_wal_file;

-- WAL size and retention
SELECT 
    COUNT(*) AS wal_files,
    pg_size_pretty(SUM(size)) AS total_size,
    MIN(file_created) AS oldest_file,
    MAX(file_created) AS newest_file
FROM pg_ls_waldir();

-- Replication slots (if using streaming replication)
SELECT 
    slot_name,
    plugin,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots;

-- -----------------------------------------------------------------------------
-- SECTION 8: VACUUM & ANALYZE
-- -----------------------------------------------------------------------------

-- VACUUM progress (if running)
SELECT 
    pid,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    ROUND(100.0 * heap_blks_scanned / NULLIF(heap_blks_total, 0), 2) AS percent_complete
FROM pg_stat_progress_vacuum;

-- ANALYZE progress
SELECT 
    pid,
    relid::regclass AS table_name,
    phase,
    sample_blks_total,
    sample_blks_scanned,
    ROUND(100.0 * sample_blks_scanned / NULLIF(sample_blks_total, 0), 2) AS percent_complete
FROM pg_stat_progress_analyze;

-- -----------------------------------------------------------------------------
-- SECTION 9: LOCK MONITORING
-- -----------------------------------------------------------------------------

-- Active locks
SELECT 
    pid,
    relation::regclass AS table_name,
    mode,
    granted,
    fastpath,
    query
FROM pg_locks l
JOIN pg_stat_activity a ON l.pid = a.pid
WHERE NOT l.granted
ORDER BY l.pid;

-- Lock conflicts
SELECT 
    blocked.pid AS blocked_pid,
    blocked.query AS blocked_query,
    blocking.pid AS blocking_pid,
    blocking.query AS blocking_query
FROM pg_stat_activity AS blocked
JOIN pg_stat_activity AS blocking ON blocking.pid = ANY(pg_blocking_pids(blocked.pid))
WHERE blocked.cardinality(pg_blocking_pids(blocked.pid)) > 0;

-- -----------------------------------------------------------------------------
-- SECTION 10: MAINTENANCE COMMANDS
-- -----------------------------------------------------------------------------

-- REINDEX a specific table (use CONCURRENTLY for production)
-- REINDEX TABLE CONCURRENTLY core_request;

-- VACUUM a specific table
-- VACUUM (VERBOSE, ANALYZE) core_request;

-- Full database vacuum
-- VACUUM (FULL, VERBOSE, ANALYZE);

-- Analyze for query planning
-- ANALYZE VERBOSE;

-- Check for bloat and recommend actions
DO $$
DECLARE
    rec RECORD;
BEGIN
    FOR rec IN 
        SELECT 
            schemaname,
            relname AS table_name,
            pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
            ROUND(100 * (pg_total_relation_size(relid) - pg_relation_size(relid)) 
                  / NULLIF(pg_relation_size(relid), 0), 2) AS bloat_percent
        FROM pg_stat_user_tables
        WHERE schemaname = 'public'
          AND pg_total_relation_size(relid) - pg_relation_size(relid) > 10 * 1024 * 1024
        ORDER BY pg_total_relation_size(relid) - pg_relation_size(relid) DESC
        LIMIT 10
    LOOP
        RAISE NOTICE 'Table % has % bloat. Run: VACUUM (VERBOSE, ANALYZE) %.%;',
            rec.table_name, rec.bloat_percent, rec.schemaname, rec.table_name;
    END LOOP;
END $$;

-- =============================================================================
-- END OF MONITORING QUERIES
-- =============================================================================
