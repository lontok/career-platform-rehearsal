# AWS EC2 and RDS migration implementation plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

Goal: Move the site from Railway to one EC2 server running the app behind Nginx and a Single-AZ RDS PostgreSQL database in your own AWS account, check it on a test subdomain, and cut the domain over before the Railway trial expires.

Architecture: The app code doesn't change. Uvicorn runs under systemd on `127.0.0.1:8000` as a non-root user, and Nginx handles HTTPS in front of it. RDS is private and accepts connections only from the server's security group, so the restore runs on the server. The tasks follow the course guide's sections in order, and each task names its section.

Tech stack: Python 3.12, uv with uv.lock, FastAPI, SQLAlchemy 2, Alembic, psycopg 3, pytest, Ubuntu 26.04 on EC2 t3.micro, RDS PostgreSQL 18.6 on db.t4g.micro, Nginx, certbot, AWS CLI 2.39, and the Cloudflare `cf` CLI.

Spec: The course guide https://raw.githubusercontent.com/LMU-ISBA/isba-4775-fa26/main/guides/aws-migration.md (downloaded 2026-11-03), the request ("Use EC2 for the app and a Single-AZ RDS PostgreSQL database. Work on a new branch so Railway doesn't redeploy from main. Don't create anything yet."), and the decisions below. Where this plan and the guide disagree, the guide wins, and the difference goes in `migration-notes.md`.

## Decisions

| Decision | Choice |
|---|---|
| Account | Your own AWS account, with the course policy attached to your IAM user |
| Architecture | EC2 with Single-AZ RDS. You accept another service and its cost in exchange for AWS running the database. |
| DNS | Records point straight at the Elastic IP, DNS only |
| Deploys | By hand over SSH |
| Cutover | Thursday afternoon, November 5 |
| Railway | Its deployment stops at cutover and restarts only to roll back. The Railway trial ends at the end of this week. |
| If AWS isn't working when the trial ends | Accept downtime and fix AWS. No paid Railway extension. |
| Acceptable data loss and recovery time | Up to a day of content changes, with recovery within a day. RDS keeps 7 days of backups, and the dumps are a second copy outside AWS. |

## Global constraints

- Every step that creates, changes, or deletes anything in AWS, Cloudflare, Railway, or GitHub waits for your go-ahead in that session. Approving one task doesn't approve the next.
- AWS work runs as your IAM user in `us-east-1`. Set `export AWS_PROFILE=isba-4775-test AWS_REGION=us-east-1` in each shell. The guide calls the profile `isba-4775`, so use whichever name you created. Only the budget and the credit checks use the root login.
- Name every resource `career-platform-*` and tag it `Project=career-platform`. Saved IDs live in `~/.config/career-platform/aws-ids.env`.
- EC2: t3.micro, Ubuntu Server 26.04 LTS x86_64 from the SSM parameter `/aws/service/canonical/ubuntu/server/26.04/stable/current/amd64/hvm/ebs-gp3/ami-id` (the "server" image, not "pro-server"), us-east-1a, `HttpTokens=required`, `CpuCredits=standard`, and a 20 GB encrypted gp3 root volume.
- RDS: `career-platform-db`, PostgreSQL 18.6, db.t4g.micro, 20 GB encrypted gp3, Single-AZ in us-east-1a, not publicly accessible, autoscaling off, 7-day automated backups, master user `cp_admin`, and database `career_platform`.
- Database connections use the default `sslmode=prefer`. Don't add `sslmode=disable` or `verify-full` to the URL.
- No seed script and no Azure deploy script run on AWS. Restore first, then run migrations, which should change nothing.
- Cloudflare: section 10 adds one A record, `aws`. Section 11 changes only the apex record. Mail, `www`, and every other record stays as it is. Save the zone's records as JSON before any change.
- Secrets live in `~/.config/career-platform/` on your laptop (mode 600) and in `/etc/career-platform/` on the server. Never put them in the repo, in chat, or in Git.
- Work stays on branch `aws-ec2-rds-migration`. Railway deploys from `main`, so nothing merges until you ask. Check Railway's connected branch before every push.
- Commit messages carry no Claude attribution lines. Prose follows the repo's voice rules: no em dashes, no semicolons, sentence-case headings, and straight quotes.
- `uv run ruff format --check .`, `uv run ruff check .`, and `uv run pytest -q` pass after every code task. pytest stays on SQLite.
- Log every change from this plan in `migration-notes.md` at the repo root, with the date and the reason.
- Expected cost: about $26.82 a month. That's EC2 $7.59, the 20 GB root volume $1.60, public IPv4 $3.65, RDS $11.68, and RDS storage $2.30. Backups and data transfer fall within the free allowances.

## Review focus

1. Content edited on Railway after the final dump never reaches AWS. Section 11 stops the Railway deployment right after that dump, and the row comparison runs before DNS moves.
2. Running migrations before the restore makes the restore fail with "already exists." Task 9.3 restores into an empty database first, and `restore-postgres.sh` refuses a database that has tables (tested in Task 9.1).
3. Page links must use https. Uvicorn trusts `X-Forwarded-Proto` only from `127.0.0.1` by default. Task 9.1 tests that the unit adds no `--forwarded-allow-ips`, and section 10 checks the HTML for `http://` links.
4. The section 10 test record exists only on AWS. Section 11 deletes it before cutover.
5. A server reboot must bring back the app and Nginx. Section 10 reboots the server and checks.

---

## Section 1: Budget

- [x] Architecture compared and chosen (the Decisions table).
- [ ] Task 1.1 (root login): In Cost Management, check your plan type, credits, and expiry. Create a budget using the template "Zero spend budget," keep the default name, and enter your email. If your account isn't on the Free plan, create a Monthly cost budget of $10 instead. Record the plan, credits, and expiry in `migration-notes.md`.

## Section 2: Back up before an outage

- [x] Railway dump and restore drill, 2026-10-29: `docs/evidence/railway-backup-restore-drill-2026-10-29.md`. Recovery point 19:48 UTC. A fresh dump comes in section 11.

## Sections 3 to 6: IAM user, CLI, policy, and plan

- [x] IAM user with MFA. CLI 2.39.1 with profile `isba-4775-test` in us-east-1. Course policy attached and tested on 2026-11-03, including restores and the public-database denies.
- [x] Blind spot pass, interview, this plan, and the cost estimate.

## Section 7: RDS database

- [x] Security groups, 2026-11-03. `career-platform-web` (sg-0c8fb344130557b1e) allows 22 from your IP only, plus 80 and 443 from anywhere. `career-platform-db` (sg-04e7733ccae6f3c35) allows 5432 from the web group only.
- [x] `career-platform-db` created 2026-11-03 with the settings above. Its master password is in `~/.config/career-platform/rds-master-password`.
- [ ] Task 7.1: In the RDS console, verify the endpoint, class, Single-AZ, and Publicly accessible: No. Save `RDS_HOST` to `aws-ids.env`.

## Section 8: EC2 instance

Gate: you approve one key pair, one t3.micro, and one Elastic IP.

- [x] Task 8.1: Generate the key on your laptop. The policy doesn't let AWS create it, so the private key never leaves your laptop.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/career-platform-aws -C career-platform-aws
aws ec2 import-key-pair --key-name career-platform-aws --public-key-material fileb://$HOME/.ssh/career-platform-aws.pub \
  --tag-specifications 'ResourceType=key-pair,Tags=[{Key=Project,Value=career-platform}]'
```

- [x] Task 8.2: Launch the server.

```bash
. ~/.config/career-platform/aws-ids.env
AMI="$(aws ssm get-parameter --name /aws/service/canonical/ubuntu/server/26.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
  --query Parameter.Value --output text)"
SUBNET="$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" Name=availability-zone,Values=us-east-1a \
  --query 'Subnets[0].SubnetId' --output text)"
INSTANCE_ID="$(aws ec2 run-instances --image-id "$AMI" --instance-type t3.micro --key-name career-platform-aws \
  --subnet-id "$SUBNET" --security-group-ids "$WEB_SG" \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled --credit-specification CpuCredits=standard \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=20,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=career-platform-web},{Key=Project,Value=career-platform}]' \
    'ResourceType=volume,Tags=[{Key=Project,Value=career-platform}]' \
  --query 'Instances[0].InstanceId' --output text)"
```

  If the launch is denied, decode the message with `aws sts decode-authorization-message` to see which rule fired.
- [x] Task 8.3: Allocate and attach the Elastic IP. Save `INSTANCE_ID`, `ALLOCATION_ID`, and `EIP` to `aws-ids.env`.

```bash
ALLOCATION_ID="$(aws ec2 allocate-address --domain vpc \
  --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Project,Value=career-platform}]' --query AllocationId --output text)"
aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOCATION_ID"
EIP="$(aws ec2 describe-addresses --allocation-ids "$ALLOCATION_ID" --query 'Addresses[0].PublicIp' --output text)"
```

- [x] Task 8.4: Before the first SSH connection, compare host keys. Take the ED25519 fingerprint from `aws ec2 get-console-output --instance-id "$INSTANCE_ID" --latest --output text` (between `BEGIN SSH HOST KEY FINGERPRINTS` and `END`). Compare it with `ssh-keyscan -t ed25519 "$EIP" | ssh-keygen -lf -`. They must match.
- [x] Task 8.5: Verify in the console and the CLI: instance ID, t3.micro, `HttpTokens` required, credits standard, the Elastic IP attached, security group `career-platform-web`, and a 20 GB encrypted gp3 volume.

## Section 9: Deploy and restore

Do Tasks 9.1 and 9.2 on your laptop before touching the server.

- [x] Task 9.1: Test and commit the PostgreSQL scripts. Create `tests/test_postgres_scripts.py` with a `stub_path(tmp_path, scripts) -> dict[str, str]` helper. The helper writes executable bash stubs into `tmp_path / "bin"`, puts that directory first on `PATH`, and logs each call to `tmp_path / "calls.log"`. Add these tests:
  - `test_backup_keeps_a_private_verified_dump`: exit 0, one `resume-*.dump` on stdout, file mode 600, and directory mode 700.
  - `test_backup_deletes_a_dump_missing_a_table`: exit 65, stderr names `profiles`, and no files remain.
  - `test_backup_deletes_the_file_when_pg_dump_fails`: exit nonzero, and no files remain.
  - `test_restore_refuses_a_target_with_tables`: exit 73, and no `pg_restore` call is logged.
  - `test_restore_loads_an_empty_target_in_one_transaction`: the logged call has `--single-transaction`, `--exit-on-error`, and `--no-owner`.
  - `test_restore_missing_backup_file`: exit 66.
  - In `tests/test_deploy_assets.py`, `test_systemd_trusts_forwarded_headers_from_loopback_only`: the unit doesn't contain `forwarded-allow-ips`.

  Run the format, lint, and test commands. Commit the tests, both scripts, the README backup section, and the October 29 evidence file: `git commit -m "feat: add tested PostgreSQL backup and restore scripts"`.
- [x] Task 9.2: Add `deploy/nginx/career-platform-http.conf`. It's a port-80 server with `server_name your-domain.example;` and the same `location /` proxy block as `career-platform.conf`. `certbot --nginx` adds HTTPS to it in section 10. Add `test_http_config_proxies_to_loopback`: contains `listen 80;` and `proxy_pass http://127.0.0.1:8000;`, and doesn't contain `listen 443`. Commit: `git commit -m "feat: add the port-80 Nginx config certbot upgrades"`. With your go-ahead, check that Railway's connected branch is `main`, then push the branch.
- [x] Task 9.3: On the server, as `ubuntu`, follow the repo's Azure runbook (`deploy/README.md` sections 2 to 4) for packages, the `career-platform` service user, `/srv/career-platform`, and `/etc/career-platform`. Make these changes from the runbook:
  - Install `postgresql-client` instead of `sqlite3`. Ubuntu 26.04's client is version 18. Check that `pg_restore --version` prints 18 or later.
  - Clone with `--branch aws-ec2-rds-migration`.
  - Write `/etc/career-platform/environment` (640, root:career-platform) with `DATABASE_URL=postgresql://career_platform:<app password>@<RDS_HOST>:5432/career_platform`. Generate the app password on the laptop into `~/.config/career-platform/rds-app-password`, and copy it over SSH from stdin so it never appears in a command line.
  - Skip the runbook's seed and its `deploy.sh`.
- [x] Task 9.4: Restore from the server.
  - Copy `data/backups/resume-20261029T194805Z-1.dump` to the server with `scp` and check its SHA-256.
  - Copy the master password to `/home/ubuntu/.rds-master-password` (mode 600).
  - As `cp_admin`, run `CREATE ROLE career_platform LOGIN PASSWORD :'app_pw'` and `ALTER DATABASE career_platform OWNER TO career_platform`, passing the app password as a psql variable read from a file.
  - Run `deploy/scripts/restore-postgres.sh <dump> "$DATABASE_URL"` as `career-platform` with the environment file loaded.
  - Run `uv sync --locked --no-dev` and `uv run alembic upgrade head`. They should change nothing.
  - Delete the master password file from the server.
- [x] Task 9.5: Install the systemd unit and run `systemctl enable --now career-platform`. Install `career-platform-http.conf` as the only enabled Nginx site, with `server_name aws.<your domain>;`. Then run `systemctl enable nginx`. Use sections 4 and 6 of the VM guide for service and log checks, with the EC2 security group in place of the Azure rule. Production DNS stays unchanged.

## Section 10: Verify on a test subdomain

Gate: you approve adding the `aws` A record in Cloudflare.

- [x] Task 10.1: Save the zone's records to `data/backups/cloudflare-records-2026-11-04.json`. Add an A record `aws` pointing at `$EIP`, DNS only. Leave every other record alone.
- [x] Task 10.2: Add HTTPS for `aws.<your domain>` with sections 3 to 6 of the HTTPS guide. Run `sudo apt-get install -y certbot python3-certbot-nginx`, then `sudo certbot certonly --nginx --dry-run -d aws.<your domain>`, then `sudo certbot --nginx -d aws.<your domain>`.
- [ ] Task 10.3: Check, and record evidence for each item in `migration-notes.md`. Mark anything you didn't verify.
  - The deployed commit matches `git rev-parse HEAD` on the branch. Row counts match the backup: profiles 1, skills 4, experiences 7, education 2, and the rest 0.
  - Add one test record (an unpublished skill named `aws-test-record`) with psql, restart `career-platform`, and confirm it's still there. Note it for deletion in section 11.
  - Run `sudo reboot`. Afterward, `career-platform` and `nginx` are active, and `/health` answers.
  - `/`, `/experience`, `/projects`, `/skills`, `/education`, `/contact`, `/privacy`, and `/health` return 200 at `https://aws.<your domain>`. Static assets load, `http://` redirects to `https://`, and the HTML has no `http://` links to your domain. `sudo certbot renew --dry-run` passes.
  - SSH works from your IP and times out from any other address (test with a phone hotspot). RDS says Publicly accessible: No, and its group allows only `career-platform-web`. The instance and database match the sizes in sections 7 and 8.

## Section 11: Cutover (Thursday afternoon, November 5)

Gate: you approve each external change: the DNS-01 TXT record, stopping Railway, and the apex record.

- [ ] Task 11.1: Confirm the Elastic IP is attached to `$INSTANCE_ID`.
- [ ] Task 11.2: Get the production certificate before traffic moves, with DNS-01. On the server, run `sudo certbot certonly --manual --preferred-challenges dns -d <your domain>`. Add the TXT record it shows as `_acme-challenge` in Cloudflare, wait until `dig +short TXT _acme-challenge.<your domain> @1.1.1.1` shows it, then continue certbot. Delete the TXT record afterward.
- [ ] Task 11.3: Save the zone's records to `data/backups/cloudflare-records-before-cutover-2026-11-05.json`. Take the final Railway dump as in the README section "Back up and restore the Railway database," and record its size and SHA-256. Then stop the Railway web deployment so it can't take new content. Leave Railway's Postgres running for rollback.
- [ ] Task 11.4: Stop `career-platform`. As `cp_admin`, drop and recreate `career_platform` owned by `career_platform`, then restore the final dump as in Task 9.4. `compare-rows.sh` against the final dump restored locally prints `Match.` Start the service. The section 10 test record goes away with the old copy. Confirm it's gone.
- [ ] Task 11.5: Add `<your domain>` to the Nginx `server_name` and run `sudo certbot install --nginx --cert-name <your domain>`. Change only the apex record, from the CNAME to Railway to an A record for `$EIP`, DNS only, TTL 60. If the API refuses the type change, delete the CNAME and create the A record right away.
- [ ] Task 11.6: Once `dig +short <your domain> @1.1.1.1` prints `$EIP`, rerun the Task 10.3 page checks at `https://<your domain>`. Check that `www` still redirects. Then run `sudo certbot reconfigure --cert-name <your domain> --nginx` so renewals no longer need a TXT record, and confirm `sudo certbot renew --dry-run` passes.
- [ ] Task 11.7: Rollback, if a check fails and can't be fixed in 30 minutes: restore the saved CNAME, then redeploy the Railway web service. AWS takes no content writes, so there's nothing to reconcile unless a seed ran on AWS.
- [ ] Task 11.8: Update the README Deployment section with the decision, the backup and recovery process, the verification results, the costs, and the next step. Add a test that the README names `migration-notes.md` and `restore-postgres.sh`. Commit the reviewed code and notes with no secrets or exports. A pull request and the merge to `main` wait for you to ask.
- [ ] Task 11.9: Clean up. List everything tagged `Project=career-platform` and remove anything unused. Confirm no Railway database exposure is still on (the TCP proxy stays off). Run `aws logout --profile isba-4775-test` when you're done for the day.

## Section 12: Diagram

- [ ] Task 12.1: Add a Mermaid architecture diagram to the README showing:
  - The request path: browser, Cloudflare DNS (DNS only, no proxy), the Elastic IP, Nginx on 80 and 443 with HTTPS ending there, and Uvicorn on 127.0.0.1:8000.
  - The VPC boundary, with RDS as its own box on 5432, reachable only from the web security group.
  - RDS automated backups and the dumps on your laptop.
  - SSH on 22 from your IP.
  - Railway, if it still serves traffic.

  Mark unfinished parts. Check every arrow against what's deployed.

## Recovering after Railway is gone

- If the server breaks, fix it over SSH, or launch a new one with sections 8 and 9 and point the A record at the Elastic IP.
- If data is lost, restore RDS to a point in time within the last 7 days. Run `aws rds restore-db-instance-to-point-in-time --source-db-instance-identifier career-platform-db --target-db-instance-identifier career-platform-db-restored --restore-time <UTC time> --db-instance-class db.t4g.micro --no-publicly-accessible --no-multi-az --availability-zone us-east-1a --vpc-security-group-ids "$DB_SG"`. Point `DATABASE_URL` at the new endpoint, then delete the old instance with a final snapshot. The policy denies a restore that leaves out the class or the public flag.
- If RDS backups can't help, restore the newest dump into an empty database with `restore-postgres.sh`. Keep the final Railway dump on your laptop until the site has run cleanly for a week.
- If you can't SSH in, update the port 22 rule with your new IP.
