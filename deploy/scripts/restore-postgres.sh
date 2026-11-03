#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
    echo "Usage: $0 <backup-file> <target-database-url>" >&2
    echo "The target database must exist and hold no tables." >&2
    exit 64
fi

backup_file="$1"
target_url="$2"

if [[ ! -f "$backup_file" ]]; then
    echo "Backup file does not exist or is not a regular file: $backup_file" >&2
    exit 66
fi

# Restoring over live data would mix two copies, so an occupied target is refused.
table_count="$(psql --no-psqlrc --tuples-only --no-align --dbname="$target_url" \
    --command="SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")"
if [[ "$table_count" != "0" ]]; then
    echo "Refusing to restore into a database that already has $table_count tables." >&2
    exit 73
fi

# One transaction, so a failed restore leaves the target empty.
pg_restore --no-owner --no-privileges --exit-on-error --single-transaction \
    --dbname="$target_url" "$backup_file"

echo "Restored $backup_file"
