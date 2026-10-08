# Move the resume site to Railway and PostgreSQL

Status: awaiting Greg's review
Date: 2026-10-07
Audience: Greg, and later the ISBA 4775 students who will repeat this move on their own sites

## 1. Purpose

The site runs today on an Azure VM, with Uvicorn behind Nginx and a SQLite file in the checkout. Each deploy is a hand-run sequence over SSH: back up, pull, sync, migrate, restart. The VM only accepts SSH from two fixed addresses, so a laptop on a new network can't reach it at all. Students will deploy to Railway with Railway's PostgreSQL, and this repo is the rehearsal they'll follow. The rehearsal has to make the same move.

This spec covers the move itself. After it, greglontok.com is served by Railway, the database is a Railway PostgreSQL service, and a push to main deploys. Local development and the test suite stay on SQLite. Where students develop later, and whether they run a local PostgreSQL, is a separate decision and not part of this change.

## 2. Goals

1. Serve greglontok.com from Railway with HTTPS, with no change to what visitors see.
2. Store all resume content in a Railway PostgreSQL service, created from the Alembic migrations and the seed.
3. Deploy from the main branch on push, with migrations and seed run before the new version takes traffic.
4. Keep SQLite working for local runs and for pytest, so nothing a student does today breaks.
5. Prove the PostgreSQL path with a real database before the domain moves.
6. Keep a rollback at every step until the VM is deleted.

## 3. Non-goals

- A local PostgreSQL for development or a devcontainer. Out of scope, by Greg's decision on 2026-10-07.
- Moving lontok.xyz or its VM. That VM stays as it is.
- Storing or emailing contact-form submissions. The form still echoes and saves nothing.
- A Dockerfile. Railway's Railpack builder reads pyproject.toml and uv.lock, which is enough.
- Removing the VM runbook and the SQLite backup and restore scripts. They stay as the legacy path until a later cleanup.

## 4. What the app looks like today

The app reads one setting, DATABASE_URL, through the Settings class in app/core/config.py. SQLAlchemy 2 models and four Alembic migrations define the schema, and app/seed.py holds every published record. Re-running the seed is safe and rebuilds the content, so there's no production data to copy. The contact form stores nothing. A fresh database plus migrate and seed reproduces the whole site.

Four spots assume SQLite and would break on PostgreSQL:

1. The profile table's single-published index uses sqlite_where only. On PostgreSQL that becomes a plain unique index on the published column, and the second unpublished profile would be refused. The seed unpublishes other profiles, so this breaks the seed.
2. Migration 20260917_02 compares the boolean published column to 0 and 1 in raw SQL. PostgreSQL rejects an integer compared to a boolean.
3. tests/test_migrations.py and the two deploy scripts open the SQLite file directly. They're correct for the VM and don't need to run on PostgreSQL, but they can't be the proof that PostgreSQL works.
4. No PostgreSQL driver is installed.

Nothing in the repo knows about Railway. The start command is fixed to port 8000, and /health exists already.

## 5. Design

### 5.1 Code changes for PostgreSQL

Add psycopg, the PostgreSQL driver for SQLAlchemy 2, to the project dependencies. Railway hands the app a DATABASE_URL that starts with postgresql://. SQLAlchemy would pick an older driver for that scheme, so Settings gains a small step that rewrites postgresql:// to postgresql+psycopg:// and leaves every other URL alone. The rewrite is the only place the app treats PostgreSQL differently, and it has its own test.

The single-published index on profiles gets a postgresql_where clause beside the sqlite_where one, both reading published is true. The model and migration 02 both declare the index, so both change.

Migration 02's four raw UPDATE statements that compare published to 0 or 1 are rewritten with SQLAlchemy expressions and bound booleans. Migration 04 compares strings and dates as text, which PostgreSQL accepts, so it stays. The SQLite foreign-key listener in app/db/session.py already returns early for any non-SQLite connection, so it stays too.

### 5.2 Railway configuration in the repo

A railway.json at the repo root carries the service settings as code, so a student can read what Railway does instead of clicking through settings:

- The start command runs Uvicorn through uv on host 0.0.0.0 and the PORT variable Railway injects.
- The pre-deploy command runs alembic upgrade head, then the seed. Railway runs it in a separate container with the service's variables before the new version takes traffic, and a failure there stops the deploy.
- The health check path is /health, so Railway only routes traffic once the app answers.
- The restart policy is on failure.

The seed in pre-deploy means every deploy rebuilds content from app/seed.py. That's the contract the README already states for content updates.

Railpack detects a Python project from pyproject.toml and installs from uv.lock. Only the main dependency group is installed, which matches the VM's no-dev sync.

### 5.3 Proof against a real PostgreSQL

One new pytest module runs only when a POSTGRES_TEST_URL variable is set, and skips otherwise. Against that database it drops any existing tables, upgrades from empty to head, and seeds. Then it downgrades one step and checks that linked rows survive, the same check the SQLite migration test makes. Greg runs it once from the laptop against the Railway database's public URL before the domain moves. Without the variable, pytest stays green on SQLite, so nothing changes for a student who hasn't set it.

### 5.4 Railway project and cutover

The Railway side is done in the dashboard, in this order, and each step is checked before the next:

1. Create a project with a PostgreSQL service.
2. Add a web service deployed from the GitHub repo's main branch. Set DATABASE_URL on it as a reference to the PostgreSQL service's own DATABASE_URL, which keeps traffic on Railway's private network.
3. Let the first deploy run. Check the build log for the uv install and the pre-deploy log for the four migrations and the seed. Then open the Railway-provided domain and check the home page, /experience, /contact, and /health.
4. Run the PostgreSQL proof test from the laptop against the database's public URL.
5. Add greglontok.com and www.greglontok.com as custom domains on the web service. Railway gives a CNAME target.
6. At the registrar, lower the TTL on the A record a day ahead, then replace the A record and the www record with the CNAME. Wait for Railway to show the certificate issued, then check https://greglontok.com answers from Railway and that http redirects to https.
7. Deallocate the test VM. Leave its resource group for a week, then delete it.

The lontok.xyz VM is not touched at any step.

### 5.5 Docs

The README's deployment section describes Railway as the deploy path and points at deploy/README.md as the legacy VM runbook. The .env example gains a commented line showing the PostgreSQL URL shape. PRODUCT.md's operating context changes from an Azure VM reached by IP to Railway at greglontok.com. The untracked VM plan docs are left alone.

## 6. Failure handling and rollback

- A failed build or pre-deploy on Railway never takes traffic. The previous deploy keeps serving. The fix is a commit to main.
- Until step 6 of the cutover, nothing public has changed. Rollback is stopping work on Railway.
- After step 6 and before the VM is deleted, rollback is putting the A record back and starting the VM. The lowered TTL keeps that under an hour.
- If the database is unreachable at runtime, the home page already falls back to app/fallback_profile.json and other pages show the generic error page. That behavior is unchanged and is tested today.

## 7. Testing

- Unit tests for the URL rewrite: postgresql:// becomes postgresql+psycopg://, and sqlite and already-prefixed URLs pass through.
- A test that the profile index declares both a sqlite_where and a postgresql_where clause.
- The existing SQLite migration test keeps passing, which covers the rewritten migration 02 on SQLite.
- The PostgreSQL proof module, run by hand against Railway before cutover and skipped elsewhere.
- The release checklist in the README still passes on SQLite. ruff format, ruff check, and pytest run clean.

## 8. Acceptance criteria

1. https://greglontok.com serves the site from Railway, with a valid certificate, and http redirects to https.
2. The Railway PostgreSQL database is at Alembic head and holds the seeded profile, 7 experiences, 4 skills, and 2 education records.
3. A push to main builds, runs migrations and seed, and takes traffic only after /health answers.
4. pytest passes on SQLite with no PostgreSQL available.
5. The PostgreSQL proof test passed against the Railway database before DNS changed.
6. The test VM is deallocated and the lontok.xyz VM is unchanged.
7. README, .env.example, and PRODUCT.md describe the Railway setup.

## 9. Decisions recorded

- Purpose is the course rehearsal, so the setup is what students can repeat. Greg, 2026-10-07.
- greglontok.com moves, lontok.xyz stays. Greg, 2026-10-07.
- Local development and pytest stay on SQLite. A local PostgreSQL is a separate, later decision. Greg, 2026-10-07.
- Content is rebuilt from the seed on every deploy rather than copied from the VM's SQLite file, because the seed is already the source of truth.
- Railpack rather than a Dockerfile, to keep one less file for students to learn before they need it.
