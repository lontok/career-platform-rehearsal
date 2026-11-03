# Career Platform

A database-driven personal resume website for analytics and technical roles.

## Run locally in Codespaces

```bash
uv sync --all-groups
mkdir -p data
cp .env.example .env
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Visit `/health` to confirm the application is running.

## Release verification

From a new Codespaces checkout, create the local database and run this exact
release checklist through the test suite:

```bash
uv sync --all-groups
mkdir -p data
uv run alembic upgrade head
uv run python -m app.seed
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

With the server running, manually inspect `/`, `/experience`, `/projects`, a
valid project URL such as `/projects/career-platform`, `/skills`, `/education`,
`/contact` (submit it once empty and once filled in),
`/health`, and an invalid project URL. Also perform a backup and restore drill
without using an existing target:

```bash
mkdir -p data/backup-verification
bash deploy/scripts/backup-sqlite.sh data/resume.db data/backup-verification
BACKUP_FILE="$(find data/backup-verification -type f -name '*.db' -print -quit)"
test -n "$BACKUP_FILE"
bash deploy/scripts/restore-sqlite.sh "$BACKUP_FILE" data/restored-resume.db
sqlite3 data/restored-resume.db "PRAGMA integrity_check;"
rm data/restored-resume.db
```

## Initialize the SQLite schema

```bash
mkdir -p data
cp .env.example .env
uv run alembic upgrade head
```

`DATABASE_URL` is loaded through `app.core.config.Settings`, so update `.env` when you want a different SQLite file location.

Do not commit SQLite database files. Keep local SQLite database files under `data/`; the repository ignores database files there (`*.db`, `*.db-wal`, `*.db-shm`, `*.db-journal`, plus matching `*.sqlite3` sidecar files). The `data/` directory itself is not globally ignored.

## Seed published resume content

```bash
uv run python -m app.seed
```

The seed command validates `app/fallback_profile.json` before writing and then inserts or updates the site owner's published records for the profile, experience, project, skill, and education tables. Records removed from the seed data are unpublished, not deleted. Re-running it is safe and doesn't create duplicates. Tests use the fictional sample in `tests/seed_samples.py` instead.

Target roles are optional. Leave `target_roles` empty when the site shouldn't read as a job search, and the home page omits them.

Seeding refuses to write when the profile's headline, summary, or location is blank. The fallback profile follows the same rule. The home page leads with the headline and summary, so a blank one leaves the first screen empty.

Seeding also unpublishes every other profile and publishes the one in `app/seed.py`. If your database holds a profile you added another way, running the seed replaces it on the public site.

## Contact form

`/contact` shows a form with Name, Email, and Message. It posts to `/contact`, checks each field, and shows the sender what they submitted. Nothing is saved or emailed yet, and the confirmation page says so. Jinja escapes every value, so HTML typed into the form displays as plain text. Names can be up to 100 characters, email addresses up to 254, and messages up to 5000. The limits live in `app/services/contact.py`, and the form's `maxlength` attributes read from the same values.

## How the home page chooses what to show

The home page shows experiences marked `featured`. When none are featured, it shows the three most recent roles. The career timeline always shows every published role, and featured roles are drawn in a different color.

The executive summary lists up to four accomplishments that have a `metric`, in the same order as the experience list. Accomplishments without a metric still appear on `/experience`.

## Update resume content safely

1. Back up the current SQLite file in `data/` before making content changes.
2. Edit the published seed content in `app/seed.py`; update `app/fallback_profile.json` only with intentionally public fallback profile data.
3. If the schema changes, create and apply a migration before seeding. To highlight a role on the home page, set `featured` to true on that experience.
4. Run `uv run alembic upgrade head`.
5. Run `uv run python -m app.seed`.
6. Confirm the public resume pages render the updated published data once the page routes are available.

Ordinary resume content updates should stay in the database seed and fallback data files; they must not require template edits.

Avoid `op.batch_alter_table` in migrations for any table that other tables point to, such as `experiences`, `skills`, or `projects`. On SQLite, batch mode rebuilds the table by dropping the old one. Migrations run with foreign keys on, so that drop deletes every linked row in tables declared `ON DELETE CASCADE`, such as accomplishments and skill links. Use `op.add_column`, which changes the table in place. `tests/test_migrations.py` upgrades a database that holds linked rows and fails if any go missing.

## Manual accessibility smoke checks

Before publishing a content update, confirm:

- Keyboard-only navigation reaches every navigation and content link.
- Keyboard focus remains visible on every interactive element.
- The mobile layout is readable without horizontal scrolling.
- Every page has one main heading.
- Links have descriptive text rather than bare URLs or ambiguous labels.
- Optional details never leave an empty label behind.

## Deployment

Since November 3, 2026, https://greglontok.com runs on AWS in us-east-1. The app runs on one EC2 server behind Nginx, and its rows live in a Single-AZ RDS PostgreSQL database. Before that it ran on Railway, which is now the rollback until its trial ends. `migration-notes.md` logs the move step by step, including every change from the plan in `docs/superpowers/plans/2026-11-02-aws-ec2-rds-migration.md`.

### Why EC2 with RDS

I chose EC2 with RDS over EC2 with PostgreSQL on the same server because I wanted AWS to run the database's backups and patching. I accept another service to manage and about $14 a month more for it. Lambda with API Gateway was the third option, but it would have meant changing how the app handles requests and database connections.

### How a request reaches the site

```mermaid
flowchart LR
    visitor["Visitor's browser"]
    admin["Laptop<br/>SSH key, passwords,<br/>dump copies"]

    subgraph cloudflare["Cloudflare"]
        dns["DNS only, grey cloud<br/>greglontok.com A 52.45.148.7<br/>aws.greglontok.com A 52.45.148.7"]
        www["www.greglontok.com<br/>proxied, 301 to the apex"]
    end

    subgraph aws["AWS us-east-1, default VPC, us-east-1a"]
        subgraph websg["Security group career-platform-web"]
            subgraph ec2["EC2 t3.micro, Ubuntu 26.04<br/>Elastic IP 52.45.148.7"]
                nginx["Nginx<br/>HTTPS ends here<br/>Let's Encrypt certificates"]
                app["Uvicorn as user career-platform<br/>127.0.0.1:8000 only"]
                dumps[("/var/backups/career-platform<br/>pg_dump files")]
            end
        end
        subgraph dbsg["Security group career-platform-db"]
            rds[("RDS PostgreSQL 18.6<br/>db.t4g.micro, Single-AZ<br/>not publicly accessible")]
        end
        snapshots[("RDS automated backups<br/>daily, kept 7 days")]
    end

    railway["Railway<br/>rollback only, no DNS points here"]

    visitor -. "1. DNS lookup" .-> dns
    visitor -- "2. HTTPS 443, or HTTP 80 then 301<br/>open to anyone" --> nginx
    nginx -- "HTTP proxy" --> app
    app -- "5432 over TLS<br/>only from career-platform-web" --> rds
    rds -.-> snapshots
    admin -- "SSH 22, my IP only" --> ec2
    dumps -. "scp" .-> admin
```

The solid arrows carry traffic, and the dotted ones are lookups and backups. Cloudflare only answers the DNS lookup for the apex. The browser then connects straight to the Elastic IP, so Cloudflare never sees that traffic. Only `www` goes through Cloudflare's proxy, which redirects it to the apex.

### Deploy an update

Deploys are by hand over SSH. Nothing on AWS watches `main`. The server checks out the branch you deploy, so push it first, then run:

```bash
ssh -i ~/.ssh/career-platform-aws ubuntu@52.45.148.7
sudo -u career-platform bash -c 'set -a; . /etc/career-platform/environment; set +a
  cd /srv/career-platform
  git pull --ff-only
  bash deploy/scripts/backup-postgres.sh "$DATABASE_URL" /var/backups/career-platform
  /usr/local/bin/uv sync --locked --no-dev
  /usr/local/bin/uv run --no-sync alembic upgrade head'
sudo systemctl restart career-platform
curl -fsS https://greglontok.com/health
```

The backup runs before the migration, so a migration that goes wrong has a copy from a minute earlier. The service starts with `uv run --no-sync`, which keeps a restart from installing the dev tools or needing the internet.

A deploy never runs the seed. To change content, edit `app/seed.py`, push, deploy, and then run the seed on the server:

```bash
sudo -u career-platform bash -c 'set -a; . /etc/career-platform/environment; set +a
  cd /srv/career-platform && /usr/local/bin/uv run --no-sync python -m app.seed'
```

The seed rewrites every seeded row from `app/seed.py`, so a row changed by hand reverts unless `app/seed.py` carries the same change.

### Backups and recovery

The database is backed up three ways:

| Backup | Where | How often | Kept |
|---|---|---|---|
| RDS automated backups | AWS, outside the server | Daily from 09:00 to 09:30 UTC, plus transaction logs for point-in-time restore | 7 days |
| `pg_dump` files | `/var/backups/career-platform` on the server | Before every deploy | Until deleted |
| Final Railway dump | `data/backups/resume-20261103T205859Z-1.dump` on the laptop, outside AWS | Once, at cutover | Until the AWS site has run cleanly for a week |

I can live with losing a day of content changes. Recovery can take up to a day too. Content only changes when I run the seed, so in practice there's almost nothing to lose.

To undo a bad change, restore RDS to a point in time from the last 7 days. The course policy denies a restore that leaves out the instance class or the public flag, so pass both:

```bash
aws rds restore-db-instance-to-point-in-time --profile isba-4775-test \
  --source-db-instance-identifier career-platform-db \
  --target-db-instance-identifier career-platform-db-restored \
  --restore-time 2026-11-04T12:00:00Z --db-instance-class db.t4g.micro \
  --no-publicly-accessible --no-multi-az --availability-zone us-east-1a \
  --vpc-security-group-ids sg-04e7733ccae6f3c35
```

The restored database gets a new endpoint. Update `DATABASE_URL` in `/etc/career-platform/environment`, restart the service, then delete the old instance with a final snapshot.

To restore a dump instead, stop the service and recreate an empty `career_platform` database as `cp_admin`, owned by `career_platform`. Then run `deploy/scripts/restore-postgres.sh <dump> "$DATABASE_URL"` on the server as `career-platform`, followed by `alembic upgrade head`. RDS's master user isn't a superuser, so it needed `GRANT career_platform TO cp_admin` before it could drop the app's database. The restore of the final Railway dump took under a second.

### What was tested

Before cutover, the AWS copy ran at https://aws.greglontok.com. These checks passed, with the evidence in `migration-notes.md`:

- Every row in RDS matched the backup across all 8 tables.
- A test record survived an app restart.
- The server came back on its own after a reboot.
- All 8 pages, the static assets, the redirects, the analytics tag, and the contact form behaved the same as on Railway.
- SSH answered only from my IP, and RDS refused connections from outside its security group.
- The instance and database matched the course's size limits.

At cutover the final data matched Railway row for row, and every check passed again at https://greglontok.com.

Automatic certificate renewal is the one check still open. `certbot renew --dry-run` uses Let's Encrypt's staging service, which was down on November 3. A real renewal of the greglontok.com certificate through Nginx did succeed right after cutover. The certificates expire February 1, 2027, and the renewal timer runs twice a day.

### What it costs

| Item | Monthly |
|---|---|
| EC2 t3.micro | $7.59 |
| EC2 root volume, 20 GB gp3 | $1.60 |
| Public IPv4 for the Elastic IP | $3.65 |
| RDS db.t4g.micro, Single-AZ | $11.68 |
| RDS storage, 20 GB gp3 | $2.30 |
| Backups and data transfer | $0.00, within the free allowances |
| Total | $26.82 |

Prices are from the AWS Price List API on November 3, 2026. The course's $100 in credits covers the rest of the semester.

### Next steps

1. Stop the Railway web deployment, or let the trial end, so nothing serves stale content.
2. Rerun `sudo certbot renew --dry-run` once Let's Encrypt staging answers again.
3. Create the zero-spend budget from the root login.
4. Merge `aws-ec2-rds-migration` into `main` after Railway is stopped, since a push to `main` still redeploys Railway while it runs.
5. At the end of the semester, decide whether to keep paying, move to a cheaper host, or delete the AWS resources tagged `Project=career-platform`.

## Railway, the rollback

`railway.json` holds the Railway service settings. Every push to `main` builds the app from `uv.lock`, runs `alembic upgrade head` as the pre-deploy command, and starts Uvicorn on the port Railway assigns. Railway sends traffic to the new version only once `/health` answers. A deploy never runs the seed.

To roll back, point the apex record back at the Railway CNAME saved in `data/backups/cloudflare-records-2026-11-03-before-cutover.json`, and redeploy the Railway web service if it was stopped. AWS takes no content writes except the seed, so there's nothing to reconcile unless a seed ran on AWS after November 3.

### Update content on Railway

Copy the database's public URL from the Railway Postgres service's Variables tab, where it's called `DATABASE_PUBLIC_URL`. Then edit `app/seed.py`, push, and run the seed once from your laptop:

```bash
export RAILWAY_DATABASE_URL='postgresql://...'
DATABASE_URL="$RAILWAY_DATABASE_URL" uv run python -m app.seed
```

The seed rewrites every seeded row from `app/seed.py`. If a row on Railway was changed by hand and `app/seed.py` doesn't carry the same change, running the seed reverts it.

### Copy rows between databases

`deploy/scripts/transfer-rows.sh` copies every content row from one database to another, keeping the ids. It refuses unless both databases are at the same Alembic head and the target has no rows. `deploy/scripts/compare-rows.sh` reads both and prints every row that differs or is missing, and exits 1 if anything does. Run both from the repo root:

```bash
bash deploy/scripts/transfer-rows.sh sqlite:///data/resume.db "$RAILWAY_DATABASE_URL"
bash deploy/scripts/compare-rows.sh sqlite:///data/resume.db "$RAILWAY_DATABASE_URL"
```

Neither script prints a database URL, since the Railway one carries the password.

### Back up and restore the Railway database

`deploy/scripts/backup-postgres.sh` writes a `pg_dump` custom-format file to a directory you name, readable only by you. It checks that `pg_restore` can read the file and that it holds the resume tables, and deletes it otherwise. `deploy/scripts/restore-postgres.sh` loads a backup into an existing database in one transaction. It refuses if the target already has tables, so it can't mix two copies.

Reach the database through Railway's SSH tunnel, which works with the public TCP proxy turned off. From a folder linked with `railway link`, run this in its own terminal and leave it open:

```bash
railway connect postgres --tunnel-only -P 55440
```

It prints a URL on `127.0.0.1:55440`. Set `RAILWAY_DATABASE_URL` to that URL, and set `DOCKER_RAILWAY_URL` to the same URL with `127.0.0.1` replaced by `host.docker.internal`, so a container can reach the tunnel. Railway runs PostgreSQL 18, and `pg_dump` refuses a server newer than itself. The Homebrew client here is 14, so run both scripts in the `postgres:18` image:

```bash
PG18() { docker run --rm -v "$PWD":/work -w /work postgres:18 "$@"; }
BACKUP_FILE="$(PG18 bash deploy/scripts/backup-postgres.sh "$DOCKER_RAILWAY_URL" data/backups)"
```

On 2026-10-29, killing `railway connect` from another terminal left its `ssh` child running. Confirm with `lsof -nP -iTCP:55440 -sTCP:LISTEN` that nothing is still listening.

Test each backup by restoring it into a scratch database, never into Railway. Then compare the rows against Railway and serve the site from the copy:

```bash
docker run -d --name restore-test -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:18
docker exec restore-test createdb -U postgres restored
PG18 bash deploy/scripts/restore-postgres.sh "$BACKUP_FILE" \
  postgresql://postgres:test@host.docker.internal:55432/restored
RESTORED_URL=postgresql://postgres:test@localhost:55432/restored
bash deploy/scripts/compare-rows.sh "$RAILWAY_DATABASE_URL" "$RESTORED_URL"
DATABASE_URL="$RESTORED_URL" uv run uvicorn app.main:app --port 8001
docker rm -f restore-test
```

`compare-rows.sh` should print `Match.` Every page at http://localhost:8001 should load as it does on the live site.

## Test against PostgreSQL

`tests/test_postgres.py` runs the migrations and seed against a real PostgreSQL database when `POSTGRES_TEST_URL` is set, and skips otherwise. It drops every table in that database first, and it refuses if any profile other than the fictional sample is there. Point it only at an empty database.

## The Azure VM

[`deploy/README.md`](deploy/README.md) is the runbook for running the site on an Ubuntu Azure VM with Nginx in front. The AWS server was set up from its sections 2 to 4, with PostgreSQL in place of SQLite. The VM stays as the course's VM reference, and its SQLite backup and restore scripts still apply there.
