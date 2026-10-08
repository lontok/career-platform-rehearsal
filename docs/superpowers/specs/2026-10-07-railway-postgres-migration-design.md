# Move the resume site to Railway and PostgreSQL

Status: approved by Greg on 2026-10-07, with DNS-only Cloudflare records
Date: 2026-10-07
Audience: Greg, and later the ISBA 4775 students who will repeat this move on their own sites

## 1. Purpose

The site runs today on an Azure VM, with Uvicorn behind Nginx and a SQLite file in the checkout. Each deploy is a hand-run sequence over SSH: back up, pull, sync, migrate, restart. The VM only accepts SSH from two fixed addresses, so a laptop on a new network can't reach it at all. Students will deploy to Railway with Railway's PostgreSQL, and this repo is the rehearsal they'll follow. The rehearsal has to make the same move.

This spec covers the move itself. After it, greglontok.com is served by Railway, the database is a Railway PostgreSQL service holding the rows copied from the VM, and a push to main deploys. Local development and the test suite stay on SQLite. Where students develop later, and whether they run a local PostgreSQL, is a separate decision and not part of this change.

## 2. Goals

1. Serve greglontok.com from Railway with HTTPS, with no change to what visitors see.
2. Store all resume content in a Railway PostgreSQL service, with the rows carried over from the VM's database.
3. Deploy from the main branch on push, with migrations run before the new version takes traffic.
4. Keep seeding a separate, hand-run step, so a deploy never rewrites content.
5. Keep SQLite working for local runs and for pytest, so nothing a student does today breaks.
6. Prove the PostgreSQL schema and the copied rows against the source before the domain moves.
7. Keep the VM and its resource group after cutover, so rollback stays a DNS change.

## 3. Non-goals

- A local PostgreSQL for development or a devcontainer. Out of scope, by Greg's decision on 2026-10-07.
- Moving lontok.xyz or its VM. That VM stays as it is.
- Storing or emailing contact-form submissions. The form still echoes and saves nothing.
- A Dockerfile. Railway's Railpack builder reads pyproject.toml and uv.lock, which is enough.
- Removing the VM runbook and the SQLite backup and restore scripts. They stay as the VM path.
- Deallocating or deleting the test VM or its resource group. Both stay, by Greg's decision on 2026-10-07.

## 4. What the app looks like today

The app reads one setting, DATABASE_URL, through the Settings class in app/core/config.py. SQLAlchemy 2 models and four Alembic migrations define the schema, and app/seed.py holds the published records. The seed inserts or updates by seed key and unpublishes records it no longer lists, so re-running it is safe. The contact form stores nothing.

The VM's database is the one visitors see today. It has the seeded profile, 7 experiences, 4 skills, and 2 education records, and no accomplishments or skill links. Those rows are what move to Railway. The seed could rebuild most of them, but rebuilding isn't the same as carrying over what's live. This move is also meant to show students how to carry rows across databases.

Four spots assume SQLite and would break on PostgreSQL:

1. The profile table's single-published index uses sqlite_where only. On PostgreSQL that becomes a plain unique index on the published column, and the second unpublished profile would be refused. The seed unpublishes other profiles, so this breaks the seed.
2. Migration 20260917_02 compares the boolean published column to 0 and 1 in raw SQL. PostgreSQL rejects an integer compared to a boolean.
3. tests/test_migrations.py and the two deploy scripts open the SQLite file directly. They're correct for the VM and don't need to run on PostgreSQL, but they can't be the proof that PostgreSQL works.
4. No PostgreSQL driver is installed.

Nothing in the repo knows about Railway. The start command is fixed to port 8000, and /health exists already. DNS for greglontok.com is at Cloudflare, with an A record pointing at the VM.

## 5. Design

### 5.1 Code changes for PostgreSQL

Add psycopg, the PostgreSQL driver for SQLAlchemy 2, to the project dependencies. Railway hands the app a DATABASE_URL that starts with postgresql://. SQLAlchemy would pick an older driver for that scheme, so Settings gains a small step that rewrites postgresql:// to postgresql+psycopg:// and leaves every other URL alone. The rewrite is the only place the app treats PostgreSQL differently, and it has its own test.

The single-published index on profiles gets a postgresql_where clause beside the sqlite_where one, both reading published is true. The model and migration 02 both declare the index, so both change.

Migration 02's four raw UPDATE statements that compare published to 0 or 1 are rewritten with SQLAlchemy expressions and bound booleans. Migration 04 compares strings and dates as text, which PostgreSQL accepts, so it stays. The SQLite foreign-key listener in app/db/session.py already returns early for any non-SQLite connection, so it stays too.

### 5.2 Railway configuration in the repo

A railway.json at the repo root carries the service settings as code, so a student can read what Railway does instead of clicking through settings:

- The start command runs Uvicorn through uv on host 0.0.0.0 and the PORT variable Railway injects.
- The pre-deploy command runs alembic upgrade head and nothing else. Railway runs it in a separate container with the service's variables before the new version takes traffic, and a failure there stops the deploy.
- The health check path is /health, so Railway only routes traffic once the app answers.
- The restart policy is on failure.

The seed is not part of the deploy. A deploy changes code and schema, and content changes stay a separate step Greg runs on purpose. After the move, a content update is an edit to app/seed.py and a push. Then Greg runs the seed once from the laptop, with DATABASE_URL set to the Railway database's public URL. The README documents that sequence.

Railpack detects a Python project from pyproject.toml and installs from uv.lock. Only the main dependency group is installed, which matches the VM's no-dev sync.

### 5.3 Row transfer and comparison

Two new scripts under deploy/scripts move the rows and check the result. Both take a source URL and a target URL and work through SQLAlchemy. That lets them run SQLite to SQLite in tests and SQLite to PostgreSQL for the real move.

The transfer script refuses to run unless both databases are at the same Alembic head and every content table on the target is empty. It then copies the tables in foreign-key order, profiles, skills, experiences, experience_accomplishments, experience_skills, projects, project_skills, and education, keeping every primary key as it is. On PostgreSQL it resets each table's id sequence afterward, so the next insert doesn't collide with a copied id. It runs in one transaction and prints a count per table.

The comparison script reads every content table from both sides, ordered by primary key. It reports the row count per table and every row that differs or is missing. It exits non-zero on any difference, so it can gate the DNS change. Dates and booleans are compared as Python values, not as the text each database stores, so a SQLite 1 and a PostgreSQL true compare equal.

Before the transfer, Greg edits one row on the VM, for example one word in an experience summary, so the source differs from what the seed would produce. The comparison then proves the rows on Railway came from the VM and not from a seed run. The edit is kept, and the seed file is updated to match in a later content change.

The SQLite file reaches the laptop through the existing backup script on the VM and scp. The transfer and comparison both run from the laptop against the Railway database's public URL.

### 5.4 Proof against a real PostgreSQL

One new pytest module runs only when a POSTGRES_TEST_URL variable is set, and skips otherwise. Against that database it drops any existing tables, upgrades from empty to head, and seeds. Then it downgrades one step and checks that linked rows survive, the same check the SQLite migration test makes. Greg runs it once from the laptop against the Railway database before the transfer, and the transfer script's empty-target check means the test's rows are gone first. Without the variable, pytest stays green on SQLite, so nothing changes for a student who hasn't set it.

### 5.5 Railway project and cutover

The Railway side is done in the dashboard, in this order, and each step is checked before the next:

1. Create a project with a PostgreSQL service.
2. Add a web service deployed from the GitHub repo's main branch. Set DATABASE_URL on it as a reference to the PostgreSQL service's own DATABASE_URL, which keeps traffic on Railway's private network.
3. Let the first deploy run. Check the build log for the uv install and the pre-deploy log for the four migrations. Open the Railway-provided domain and check /health answers and the home page renders with no profile, since no rows exist yet.
4. Run the PostgreSQL proof test from the laptop against the database's public URL. Then drop its tables and run alembic upgrade head again, so the database is empty at head.
5. Back up the VM's SQLite file, copy it to the laptop, make the one-row edit on the VM, and back up again. Transfer the rows from that second backup to Railway. Run the comparison between the backup and Railway and keep its output.
6. Check the Railway-provided domain again. The home page, /experience, /skills, and /education show the same content as greglontok.com, including the edited row.
7. Add greglontok.com and www.greglontok.com as two custom domains on the web service. Railway gives each one its own CNAME value and TXT record.
8. At Cloudflare, replace the root A record with a CNAME to Railway's value for greglontok.com, and replace the www A record with a CNAME to Railway's value for www. Set both to DNS only, the grey cloud. Add both TXT records. Change nothing else in Cloudflare: no TTL change, no proxy, no SSL mode change, and no redirect. Both names serve the site, and neither redirects to the other.
9. Wait for Railway to show both domains verified and their certificates issued. Then check https://greglontok.com and https://www.greglontok.com both answer from Railway, http redirects to https on both, and the comparison still passes.
10. Leave the VM running. It is the rollback and stays as the course's VM reference.

The lontok.xyz VM is not touched at any step.

### 5.6 Docs

The README's deployment section describes Railway as the deploy path, the seed-by-hand content sequence, and the transfer and comparison scripts, and points at deploy/README.md as the VM runbook. The .env example gains a commented line showing the PostgreSQL URL shape. PRODUCT.md's operating context changes from an Azure VM reached by IP to Railway at greglontok.com. The untracked VM plan docs are left alone.

## 6. Failure handling and rollback

- A failed build or pre-deploy on Railway never takes traffic. The previous deploy keeps serving. The fix is a commit to main.
- A transfer that fails partway rolls back its transaction, and the empty-target check lets it run again from the start.
- A comparison that reports differences stops the cutover before step 7. The rows on Railway are dropped and the transfer runs again.
- Until step 8, nothing public has changed. Rollback is stopping work on Railway.
- After step 8, rollback is putting the root and www A records back at Cloudflare, both pointed at the VM. The VM is still running and its certificate covers both names, so it is back in front once the records' TTL passes.
- If the database is unreachable at runtime, the home page already falls back to app/fallback_profile.json and other pages show the generic error page. That behavior is unchanged and is tested today.

## 7. Testing

- Unit tests for the URL rewrite: postgresql:// becomes postgresql+psycopg://, and sqlite and already-prefixed URLs pass through.
- A test that the profile index declares both a sqlite_where and a postgresql_where clause.
- The existing SQLite migration test keeps passing, which covers the rewritten migration 02 on SQLite.
- Transfer tests, SQLite to SQLite in a temp directory: a full copy matches row for row, a target with rows is refused, and mismatched Alembic heads are refused.
- Comparison tests: identical databases pass, one changed cell is reported with its table and primary key, and a missing row is reported.
- The PostgreSQL proof module, run by hand against Railway before the transfer and skipped elsewhere.
- The release checklist in the README still passes on SQLite. ruff format, ruff check, and pytest run clean.

## 8. Acceptance criteria

1. https://greglontok.com and https://www.greglontok.com both serve the site from Railway, each with a certificate Railway issued, and http redirects to https on both.
2. The Railway PostgreSQL database is at Alembic head and the comparison against the VM's backup reports no differences, including the edited row.
3. A push to main builds, runs migrations, and takes traffic only after /health answers. No deploy runs the seed.
4. pytest passes on SQLite with no PostgreSQL available, and the transfer and comparison scripts have tests.
5. The PostgreSQL proof test passed against the Railway database before the transfer.
6. The test VM and its resource group still exist and the VM is running. The lontok.xyz VM is unchanged.
7. README, .env.example, and PRODUCT.md describe the Railway setup and the seed-by-hand sequence.

## 9. Decisions recorded

- Purpose is the course rehearsal, so the setup is what students can repeat. Greg, 2026-10-07.
- greglontok.com moves, lontok.xyz stays. Greg, 2026-10-07.
- Local development and pytest stay on SQLite. A local PostgreSQL is a separate, later decision. Greg, 2026-10-07.
- The seed stays out of the deploy and runs by hand. Greg, 2026-10-07.
- Rows are copied from the VM's database rather than rebuilt from the seed, with an edited row and a source-to-target comparison before DNS moves. Greg, 2026-10-07.
- The VM and its resource group stay after cutover. Greg, 2026-10-07.
- Cloudflare records are DNS only. The root and www each become a CNAME to Railway with their TXT records, and nothing else in Cloudflare changes. Greg, 2026-10-07.
- www moves to Railway with the root, as its own custom domain and with no redirect between the two. Greg, 2026-10-08.
- Railpack rather than a Dockerfile, to keep one less file for students to learn before they need it.
