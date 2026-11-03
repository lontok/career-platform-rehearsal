# Railway database backup and restore drill

Run 2026-10-29 at 19:48 UTC, before the move from Railway to AWS. The steps follow the "Back up and restore the Railway database" section of the README and Railway's restore drill guide (https://github.com/railwayapp/docs/blob/main/content/guides/postgres-backups-restores.md).

## Backup

The laptop reached the Railway Postgres service (PostgreSQL 18.6) through `railway connect postgres --tunnel-only`, so the public TCP proxy stayed off. `deploy/scripts/backup-postgres.sh` ran in the `postgres:18` image, since the Homebrew `pg_dump` is version 14 and refuses a newer server.

| Item | Value |
|------|-------|
| File | `data/backups/resume-20261029T194805Z-1.dump` (Git ignores it) |
| Size | 26,268 bytes |
| SHA-256 | `9f013aa5b95f2f721a97b1fbf272db1eb71875a15c8cbab93ad7e5bf7e5eee92` |
| Dump time | 4 seconds |

## Restore

The dump went into an empty scratch database in a local `postgres:18` container, never into Railway. `deploy/scripts/restore-postgres.sh` finished in under a second, and the copy reported Alembic revision `20261006_04 (head)`.

`deploy/scripts/compare-rows.sh` between Railway and the copy printed `Match.`:

| Table | Railway | Copy |
|-------|---------|------|
| profiles | 1 | 1 |
| skills | 4 | 4 |
| experiences | 7 | 7 |
| experience_accomplishments | 0 | 0 |
| experience_skills | 0 | 0 |
| projects | 0 | 0 |
| project_skills | 0 | 0 |
| education | 2 | 2 |

The app ran against the copy, and `/`, `/experience`, `/projects`, `/skills`, `/education`, `/contact`, `/privacy`, and `/health` each returned 200. Each page's HTML matched https://greglontok.com once hostnames and static-file version strings were removed.

## Recovery numbers

The restore took under a second. The recovery point is the dump time, 2026-10-29 19:48 UTC. Content changes on Railway after that time are not in this backup.

## Cleanup

The tunnel, the scratch container, and the tunnel output, which held the password, were removed after the drill.
