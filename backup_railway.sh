#!/bin/bash
# =============================================================================
# PLAGENOR 4.0 - Railway PostgreSQL Backup Script
# =============================================================================
# This script creates a PostgreSQL backup of your Railway database.
# 
# Usage:
#   ./backup_railway.sh                    # Interactive (will prompt for variables)
#   DATABASE_URL="..." ./backup_railway.sh  # Use environment variable
#
# Schedule with Railway Cron:
#   railway run --cron "0 2 * * *" ./backup_railway.sh
# =============================================================================

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-./backups}"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/plagenor_backup_${DATE}.sql"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== PLAGENOR Database Backup ===${NC}"
echo "Date: $(date)"
echo ""

# Get DATABASE_URL if not set
if [ -z "$DATABASE_URL" ]; then
    echo -e "${YELLOW}DATABASE_URL not set. Checking Railway environment...${NC}"
    
    # Try to get from Railway CLI
    if command -v railway &> /dev/null; then
        echo "Getting DATABASE_URL from Railway..."
        export DATABASE_URL=$(railway variables get DATABASE_URL 2>/dev/null || echo "")
    fi
    
    if [ -z "$DATABASE_URL" ]; then
        echo -e "${RED}Error: DATABASE_URL not found!${NC}"
        echo "Please set DATABASE_URL environment variable or run from Railway."
        echo ""
        echo "To get your DATABASE_URL:"
        echo "  1. Go to Railway Dashboard"
        echo "  2. Select your PostgreSQL service"
        echo "  3. Click 'Connection String'"
        echo "  4. Copy the value"
        exit 1
    fi
fi

# Parse DATABASE_URL
# Format: postgresql://user:password@host:port/database
DB_USER=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
DB_PASS=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.* @@[^:]*:\([0-9]*\).*|\1|p' | sed -n 's|.*@\([^:]*\):.*|\1|p')
DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/[^/]*$|\1|p')
DB_NAME=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^/?]*\).*|\1|p')

# Handle both formats (with and without query params)
DB_NAME=$(echo "$DB_NAME" | cut -d'?' -f1)

echo "Database: $DB_NAME"
echo "Host: $DB_HOST:$DB_PORT"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Perform backup
echo -e "${GREEN}Creating backup...${NC}"

export PGPASSWORD="$DB_PASS"

# Use pg_dump for backup
if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -F c -b -v -f "$BACKUP_FILE" 2>/dev/null; then
    echo -e "${GREEN}Backup created successfully!${NC}"
    echo "File: $BACKUP_FILE"
    echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"
else
    # Fallback to plain SQL format
    echo -e "${YELLOW}Custom format failed, trying plain SQL...${NC}"
    if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -F p -b -v -f "$BACKUP_FILE" 2>/dev/null; then
        echo -e "${GREEN}Backup created successfully!${NC}"
        echo "File: $BACKUP_FILE"
        echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"
    else
        echo -e "${RED}Backup failed!${NC}"
        exit 1
    fi
fi

# Cleanup old backups
echo ""
echo -e "${GREEN}Cleaning up old backups (keeping last $RETENTION_DAYS days)...${NC}"
find "$BACKUP_DIR" -name "plagenor_backup_*.sql" -type f -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "plagenor_backup_*.c.gz" -type f -mtime +$RETENTION_DAYS -delete 2>/dev/null || true

# List remaining backups
echo ""
echo "Current backups:"
ls -lh "$BACKUP_DIR"/plagenor_backup_* 2>/dev/null | tail -5 || echo "No backups found"

# Upload to cloud storage (optional - uncomment if using S3/R2)
# if [ -n "$BACKUP_BUCKET_URL" ]; then
#     echo ""
#     echo "Uploading to cloud storage..."
#     curl -X PUT -T "$BACKUP_FILE" "$BACKUP_BUCKET_URL/$(basename $BACKUP_FILE)"
#     echo "Upload complete!"
# fi

echo ""
echo -e "${GREEN}=== Backup Complete ===${NC}"
