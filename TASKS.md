# Tasks

## Active

- [ ] **R1: Add a "this website, in progress" project entry** - closes with: a project in `SEED_PROJECTS` in `app/seed.py`, seeded to Railway, and visible at https://greglontok.com/projects, due 2026-10-22
- [ ] **R1: Homepage returns 503 with "Projects temporarily unavailable" and the profile on database failure** - closes with: `app/routers/pages.py`, `app/services/resume.py`, and the 200 assertion in `tests/test_fallback.py` changed to 503, due 2026-10-22
- [ ] **R1: Show that refresh restores projects without a restart** - closes with: a recovery test in `tests/test_fallback.py` or a dated manual check in `docs/evidence/`, due 2026-10-22
- [ ] **R1: Explain the SQLite choice and the alternatives considered** - closes with: a decisions section in `README.md`, due 2026-10-22
- [ ] **R2: Make the tracked systemd unit match the VM's two-worker unit** - closes with: `--workers 2` in `deploy/systemd/career-platform.service`, or a note in `deploy/README.md` that the test VM uses the unit in the operate-the-VM plan, due 2026-10-22
- [ ] **R2: Record a controlled reboot of the test VM** - closes with: a dated reboot, then `/health` and page checks for greglontok.com saved in `docs/evidence/`, due 2026-10-22
- [ ] **R2: Document SSH access, public and private IPs, and NSG rules for the test VM** - closes with: `az network nsg rule list` and `az vm list-ip-addresses` output saved in `docs/evidence/`, due 2026-10-22
- [ ] **R2: Explain what made the site survive a restart** - closes with: a README paragraph on `systemctl enable` for the app and Nginx, due 2026-10-22
- [ ] **R3: Record the current DNS records and their purpose** - closes with: fresh `cf dns records list --zone greglontok.com` output in `docs/evidence/`, replacing the 2026-10-13 snapshot as the final state, due 2026-10-22
- [ ] **R3: Keep the Azure-era HTTPS and renewal evidence** - closes with: the test VM's certificate details and `systemctl status certbot.timer` output in `docs/evidence/`, due 2026-10-22
- [ ] **R3: Explain the certificate hostnames, validity, and renewal** - closes with: a README section on the root's Railway Let's Encrypt cert, which expires Jan 6 2027, and the www Cloudflare edge cert, which expires Dec 30 2026, due 2026-10-22
- [ ] **R3: Save the www redirect verification** - closes with: dated curl output showing `http://www` and `https://www` land on `https://greglontok.com/`, saved in `docs/evidence/`, due 2026-10-22
- [ ] **R4: Record dated results for Railway plan tasks 7 to 10** - closes with: ticked steps and result lines in `docs/superpowers/plans/2026-10-08-railway-postgres-migration.md`, due 2026-10-22
- [ ] **R4: Identify the edited row and confirm it reached Railway** - closes with: the seed key and new location in the plan, plus a check of whether the seed later overwrote it, due 2026-10-22
- [ ] **R4: Track the source and target row comparison** - closes with: `data/migration-copy/compare-20261008T152327Z.txt` copied into `docs/evidence/`, due 2026-10-22
- [ ] **R4: Compare the rendered page on source and target** - closes with: a dated page comparison saved in `docs/evidence/`, due 2026-10-22
- [ ] **R4: Update rollback to the current CNAME and Pro-plan setup** - closes with: a README rollback section, with data written after cutover covered, due 2026-10-22
- [ ] **R4: Compare Azure and Railway responsibilities** - closes with: a README table covering OS, runtime, web entry, TLS, code, config, database software, data, and DNS, due 2026-10-22
- [ ] **R4: Confirm the pre-deploy `alembic upgrade head` runs on Railway** - closes with: a deploy log line or the dashboard's Pre-deploy Command setting, due 2026-10-22
- [ ] **R5: Connect c2d8cca to its deployment and live result** - closes with: commit c2d8cca, Railway deployment 415681e0 from 2026-10-15, and the live `/privacy` link recorded in the submission index, due 2026-10-22
- [ ] **R5: Write how to restore a previous version for code and data** - closes with: the README rollback section, due 2026-10-22
- [ ] **R6: Complete the Ex06 results sheet with the before-MX message line** - closes with: `docs/evidence/ex06.md`, due 2026-10-22
- [ ] **R6: Add the Zoho header analysis** - closes with: `docs/evidence/zoho-header-check.md`, due 2026-10-22
- [ ] **R6: Explain MX, SPF, DKIM, and DMARC as published** - closes with: a README or `ex06.md` section on the three Zoho MX hosts, SPF, the `zmail` DKIM key, and DMARC `p=none`, due 2026-10-22
- [ ] **R7: Track one useful interaction such as an outbound link click** - closes with: GA4 enhanced measurement turned on, or a custom event in `app/templates/base.html`, due 2026-10-22
- [ ] **R7: Verify the page view and interaction in Realtime or DebugView** - closes with: a dated, redacted screenshot and explanation in `docs/evidence/`, due 2026-10-22
- [ ] **R8: Add the submission index** - closes with: `docs/project-1-submission.md` with the repo URL, live URL, final SHA, and links, due 2026-10-22
- [ ] **R8: Add AGENTS.md** - closes with: `AGENTS.md` committed at the repo root, due 2026-10-22
- [ ] **R8: Track the untracked evidence and plans** - closes with: `docs/evidence/` and both `2026-10-01-operate-the-vm` plans committed, due 2026-10-22
- [ ] **R8: Link the two investigated failures** - closes with: `docs/evidence/ex03.md` and `docs/evidence/ex05.md` in the repo and linked from the README, due 2026-10-22
- [ ] **R8: Link the Ex04 HTTPS explanation** - closes with: the Ex04 file in the repo and linked from the README, due 2026-10-22
- [ ] **R8: Add the live address to the README** - closes with: https://greglontok.com in `README.md`, due 2026-10-22
- [ ] **R8: Add Azure and Railway diagrams with email and analytics paths** - closes with: a diagram file linked from `README.md`, due 2026-10-22
- [ ] **R8: Add the decisions section** - closes with: the Railway migration and managed versus self-hosted email decisions in `README.md`, due 2026-10-22
- [ ] **R8: Add the reflection** - closes with: a reflection section in `README.md`, due 2026-10-22
- [ ] **R8: Add costs, expiration dates, and cleanup plans** - closes with: a README section on Railway Pro billing, Azure, Zoho, and domain renewal, due 2026-10-22
- [ ] **R8: Add remaining limitations** - closes with: a limitations section in `README.md`, due 2026-10-22
- [ ] **Turn off the public FastAPI docs page** - closes with: `docs_url=None` in `app/main.py`, then `/docs` returning 404 on greglontok.com

## Waiting On

## Someday

## Done
