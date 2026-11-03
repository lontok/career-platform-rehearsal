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

## Log

- 2026-11-03: Created security groups `career-platform-web` and `career-platform-db`. Created RDS `career-platform-db` (PostgreSQL 18.6, db.t4g.micro, Single-AZ us-east-1a, 20 GB encrypted gp3, not public, 7-day backups).
- 2026-11-03: Imported key pair `career-platform-aws`. Launched `career-platform-web` (t3.micro, Ubuntu 26.04.1 from ami-0bfc5cae5711ffac8, us-east-1a, IMDSv2 required, standard credits, 20 GB encrypted gp3) and attached Elastic IP 52.45.148.7. The host key fingerprint from the console output matched the live server (ED25519 SHA256:O+9cjWoU0gnWr7Z9Q22dMvubLzbHCuTRAuKdLunaDEk) before the first SSH login.
