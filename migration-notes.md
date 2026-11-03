# Migration notes

A log of the move from Railway to AWS, with every change from the plan in `docs/superpowers/plans/2026-11-02-aws-ec2-rds-migration.md` and the reason for it. No secrets, IDs of secrets, or database URLs go here.

## Deviations from the plan

| Date | Change | Reason |
|---|---|---|
| 2026-11-03 | The plan now follows the course guide's sections and settings: Ubuntu 26.04, a 20 GB encrypted root volume, `sslmode=prefer`, restoring from the server, an `aws.` test subdomain, a DNS-01 certificate, stopping Railway at cutover, and a diagram | The guide is the course's reference, and the earlier plan predated reading it |
| 2026-11-03 | The security groups and the RDS database were created Tuesday, not Wednesday | Section 7 was reached a day ahead of the plan's schedule |
| 2026-11-03 | The database exists before the section 1 budget does | Created on request before the budget step. The budget is next. |
| 2026-11-03 | The plan's Nginx template edits for webroot certificates were dropped | The HTTPS guide uses `certbot --nginx`, which writes the TLS settings itself |
| 2026-11-03 | The SSH key has no passphrase | The agent generated it in a shell that can't prompt. Add one with `ssh-keygen -p -f ~/.ssh/career-platform-aws`. |
| 2026-11-03 | The EC2 instance was launched before the section 1 budget exists | Launched on request. The budget is still the next open step. |
| 2026-11-03 | The systemd unit now starts with `uv run --no-sync uvicorn` | Plain `uv run` syncs the dev group on every start, which put test tools in production and needed the internet to boot |
| 2026-11-03 | The restore ran as the `career_platform` role, created by `cp_admin` from the server | The plan's app role. The master password went to the server over stdin into a private file, which was deleted after use. |
| 2026-11-03 | The aws.greglontok.com certificate was issued without a `certbot --dry-run` first | Let's Encrypt's staging API, which dry runs use, timed out from both the server and the laptop. Production answered in 0.13 seconds. DNS and port 80 were already verified, so one production request was made, with the plan to stop rather than retry if it failed. |
| 2026-11-03 | Certbot registered without an email address | No email was given to Let's Encrypt. Renewal runs on the certbot timer, and section 10 checks it. |
| 2026-11-03 | Cutover started Tuesday instead of Thursday | Requested. It leaves more of the Railway trial as a rollback. |
| 2026-11-03 | Cutover started with `certbot renew --dry-run` still unverified | Let's Encrypt staging was down. It affects renewal in about 60 days, not today's cutover. |
| 2026-11-03 | The DNS-01 challenge ran through a small certbot hook that waits for a flag file, and the TXT record was added and removed with the `cf` CLI from the laptop | `certbot --manual` waits for Enter, and no Cloudflare token goes on the server |
| 2026-11-03 | `cp_admin` was granted membership in `career_platform` | On RDS the master user isn't a superuser, so it can't drop a database owned by another role without that membership |
| 2026-11-03 | The Railway web deployment wasn't stopped by the agent | Claude Code's auto-mode safety check denied `railway down`. Waiting for the student's decision. |

## Log

- 2026-11-03: Created security groups `career-platform-web` and `career-platform-db`. Created RDS `career-platform-db` (PostgreSQL 18.6, db.t4g.micro, Single-AZ us-east-1a, 20 GB encrypted gp3, not public, 7-day backups).
- 2026-11-03: Imported key pair `career-platform-aws`. Launched `career-platform-web` (t3.micro, Ubuntu 26.04.1 from ami-0bfc5cae5711ffac8, us-east-1a, IMDSv2 required, standard credits, 20 GB encrypted gp3) and attached Elastic IP 52.45.148.7. The host key fingerprint from the console output matched the live server (ED25519 SHA256:O+9cjWoU0gnWr7Z9Q22dMvubLzbHCuTRAuKdLunaDEk) before the first SSH login.
- 2026-11-03: Section 9. Committed tested backup and restore scripts and the port-80 Nginx config, and pushed `aws-ec2-rds-migration` (Railway's service deploys from `main`, checked first). On the server: Ubuntu packages including pg_restore 18.6, uv 0.13.7, Python 3.12.16 from `.python-version`, the `career-platform` service user, and a clone of the branch at d390a4b.
- 2026-11-03: Restored `railway-20261029T194805Z.dump` (SHA-256 9f013aa5...ee92, matched after copy) into RDS in 0.27 seconds. `alembic upgrade head` applied 0 migrations, and the database is at `20261006_04 (head)`. Row counts match the October 29 drill: profiles 1, skills 4, experiences 7, education 2, and 0 in the other four tables. Every table is owned by `career_platform`, and the connection uses TLS (`ssl=true`) under the default `sslmode=prefer`.
- 2026-11-03: `career-platform` and `nginx` are enabled and active. Uvicorn runs as `career-platform` on 127.0.0.1:8000 only. Nginx answers `aws.greglontok.com` on port 80, `/health` returns ok from the laptop, and port 8000 refuses outside connections. No errors in either service's log. Production DNS is unchanged, and Railway still serves greglontok.com.
- 2026-11-03: Section 10. Saved the zone's 11 records to `data/backups/cloudflare-records-2026-11-03-before-aws.json` (ignored by Git). Added one A record with the `cf` CLI: `aws.greglontok.com` to 52.45.148.7, DNS only, automatic TTL. A before-and-after comparison shows that record added and nothing else removed or changed. 1.1.1.1 and 8.8.8.8 both resolve it, and `http://aws.greglontok.com/health` returns ok. The apex still points to Railway.
- 2026-11-03: Installed certbot 4.0.0 with its Nginx plugin and ran `certbot --nginx -d aws.greglontok.com --redirect`. The certificate is CN=aws.greglontok.com from Let's Encrypt YE1 and expires 2027-02-01. Certbot added the 443 server and a 301 from HTTP. Checked from the laptop: `/health` returns ok over HTTPS, `http://aws.greglontok.com/experience` returns 301 to the https URL, the certificate verifies, and the home page has no `http://` links to the host. `certbot.timer` is enabled.

## Section 10 verification, 2026-11-03

| Check | Evidence | Result |
|---|---|---|
| Deployed commit | Server at d390a4b. The branch head 157e6b0 differs only in the plan and these notes. | Verified |
| Records match the backup | The Oct 29 dump restored into a local PostgreSQL 18 container, compared with RDS through an SSH tunnel by `compare-rows.sh` | `Match.` on all 8 tables |
| Test record survives a restart | `skills` id 5, `aws-test-record`, unpublished, still present after `systemctl restart` (PID 4049 to 5837) and not shown on `/skills` | Verified. Delete before cutover. |
| Reboot | Boot ID changed, up since 20:46:32 UTC. `career-platform`, `nginx`, and `certbot.timer` active, app running as `career-platform`, test record present, no errors in either log | Verified. HTTPS answered 25 seconds after the reboot command. |
| Pages | `/`, `/experience`, `/projects`, `/skills`, `/education`, `/contact`, `/privacy`, and `/health` return 200, and an unknown project returns 404, the same as Railway. Each page's HTML matches greglontok.com once host names and asset version strings are removed. | Verified |
| Assets | `favicon.svg`, `styles.css`, and `timeline.js` return 200 with the right types | Verified |
| Redirects | `http://aws.greglontok.com/skills` returns 301 to https. The bare IP over HTTP returns 404. | Verified |
| Integrations | Google Analytics tag present. Contact form returns 400 when empty and 200 with the message echoed when filled. | Verified |
| Certificate renewal | `certbot renew --dry-run` hung because Let's Encrypt staging still timed out, and it was stopped. The timer is active and the certificate is valid to 2027-02-01. | Not verified. Rerun when staging is back. |
| SSH restricted | Port 22 allows only 172.117.89.209/32. From the server's own public address port 22 timed out while 443 connected. | Verified |
| RDS private | Publicly accessible False. The endpoint resolves to 172.31.81.45. Port 5432 is unreachable from the laptop, and its group allows only `career-platform-web`. | Verified |
| Sizes | EC2 t3.micro, IMDSv2 required, standard credits, 20 GB encrypted gp3, us-east-1a. RDS db.t4g.micro, Single-AZ, 20 GB encrypted gp3, us-east-1a, 7-day backups. | Verified |
| Ports from the internet | 22, 80, and 443 open from the allowed IP. 5432 and 8000 closed. | Verified |

## Section 11 cutover log, 2026-11-03

- 20:52 UTC: Elastic IP 52.45.148.7 confirmed attached to i-01463f87c16915b92.
- 20:55 UTC: Production certificate for greglontok.com issued by DNS-01 before any traffic moved (Let's Encrypt YE2, expires 2027-02-01). The temporary `_acme-challenge` TXT record was visible on Cloudflare's nameserver, 1.1.1.1, and 8.8.8.8 within 20 seconds, then deleted.
- 20:57 UTC: Added Nginx site `career-platform-apex` for greglontok.com, and `certbot install --redirect` added HTTPS. Through the Elastic IP with `--resolve`, `/health`, `/`, and `/experience` returned 200, and HTTP returned 301 to HTTPS.
- 20:58 UTC: Saved the zone's 12 records to `data/backups/cloudflare-records-2026-11-03-before-cutover.json`. The apex was CNAME `f6lqertk.up.railway.app`, DNS only, record ID adb246d43c21c051a9c284dd55a84f10.
- 20:59 UTC: Final Railway dump `data/backups/resume-20261103T205859Z-1.dump`, 26,268 bytes, SHA-256 735b62535e08491e725027595d859d87393d026b8c32cb654ee5ef255c992025, in 3 seconds. Recovery point 20:59:02 UTC. Checksum matched on the server.
- 21:00 UTC: Recreated `career_platform` and restored the final dump. 0 migrations applied, at `20261006_04 (head)`, and the section 10 test record is gone. `compare-rows.sh` between Railway's live database and RDS printed `Match.` on all 8 tables.
- Not done yet: stopping the Railway web deployment, the apex DNS change, production verification, and switching renewal to the Nginx method. Railway still serves greglontok.com.

