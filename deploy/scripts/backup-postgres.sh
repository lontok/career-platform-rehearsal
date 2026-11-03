#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$#" -ne 2 ]]; then
    echo "Usage: $0 <source-database-url> <backup-directory>" >&2
    echo "pg_dump must be the same major version as the server or newer." >&2
    exit 64
fi

source_url="$1"
backup_directory="$2"

mkdir -p "$backup_directory"
chmod 700 "$backup_directory"

backup_file="$backup_directory/resume-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"

# The custom format lets pg_restore list the contents, which is the check below.
trap 'rm -f -- "$backup_file"' ERR
pg_dump --format=custom --no-owner --no-privileges --file="$backup_file" "$source_url"
chmod 600 "$backup_file"

# A dump that pg_restore cannot read, or that lacks the resume tables, is not a backup.
contents="$(pg_restore --list "$backup_file")"
for table in alembic_version profiles projects experiences skills education; do
    if ! grep -q "TABLE DATA public $table " <<<"$contents"; then
        echo "Backup is missing table data for $table." >&2
        rm -f -- "$backup_file"
        exit 65
    fi
done

trap - ERR
echo "$backup_file"
