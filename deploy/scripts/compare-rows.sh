#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
    echo "Usage: $0 <source-database-url> <target-database-url>" >&2
    echo "Run from the repo root. Exits 1 if any row differs." >&2
    exit 64
fi

if [[ ! -f app/db/transfer.py ]]; then
    echo "Run this from the repo root." >&2
    exit 64
fi

exec uv run python -m app.db.transfer compare "$1" "$2"
