# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary visitor is a recruiter or hiring manager looking for analytics or technical talent in the Los Angeles area. They're scanning quickly and want to know what the candidate does, where they're based, and what evidence backs it up. Design work serves this visitor first.

The site is also a course reference build. Greg is rehearsing the ISBA 4775 project that his business analytics students will build for themselves. Students are a second audience. They'll read the site and its code as a model of a finished project, but the pages aren't designed for them.

The content owner is the candidate, who updates the site through version-controlled seed data and database scripts. There's no admin screen.

## Product Purpose

It's a database-driven personal resume site for analytics and technical roles. It exists to show that the candidate understands business needs and delivers measurable value, not only that they know a list of tools.

Success means a recruiter lands on the home page and understands the candidate from that one page. They should see the target roles, the Los Angeles connection, the value proposition, and the experience, projects, skills, and education behind it. They should also find a professional contact path through LinkedIn or GitHub.

This is the first stage of a larger career platform. Later stages could add an admin dashboard, sign-in, multiple profiles, and job tracking, but none of those exist yet.

## Positioning

The narrative runs from business need to quantified value. The home page leads with the value proposition and puts evidence second. Every claim on the site should trace back to a database record. That might be an accomplishment with a metric, or a project with a stated business problem and outcome.

## Operating Context

The recruiter reads the site in a browser on a phone or a laptop, often while comparing several candidates. They don't sign in and can't write anything back to the site.

The content owner edits `app/seed.py` and `app/fallback_profile.json`, then runs the migration and seed commands. The change deploys the same way as a code change. Ordinary content updates must never require a template edit.

The site runs locally on SQLite and in production on Railway at greglontok.com, with a Railway PostgreSQL database. A push to `main` deploys and runs migrations. Content updates run the seed by hand. The Azure VM it ran on before stays as a reference and a rollback.

## Capabilities and Constraints

- Public routes are `/`, `/experience`, `/projects`, `/projects/{slug}`, `/skills`, `/education`, and `/health`. An unknown or unpublished project slug returns the standard not-found page.
- Only records marked published appear on any public page.
- Experience sorts current roles first, then completed roles by most recent start date. A current role reads "Present."
- Empty optional fields are omitted entirely. They must never leave an empty label, a broken link, or a visible "undefined."
- The profile email is stored but never shown on the site. Contact happens through LinkedIn and GitHub links, which open safely in a new tab.
- A skill label alone must not imply professional mastery. Project and experience pages supply the context where a skill was applied.
- When the database is down, the home page renders a validated fallback profile. It shows name, headline, summary, location, target roles, and contact links, plus a message that details are temporarily unavailable. Experience, projects, skills, and education are omitted rather than served from a stale source. Any design must still hold up in this degraded state.
- Other routes return a plain generic error page when the database is down, with no stack traces, queries, or credentials.
- The first release uses FastAPI, Jinja templates, plain CSS in `app/static/styles.css`, and SQLite. Greg didn't make "no JavaScript," "content-agnostic layouts," or "self-hosted assets only" binding design constraints during init, so those remain open decisions.
- Out of scope for now: registration and sign-in, multiple profiles, a browser admin, job tracking, messaging, resume import, a blog, testimonials, a downloadable PDF resume, and visitor analytics. A contact form exists at `/contact`, but it doesn't store or send messages yet.

## Brand Commitments

The candidate's name is the site identity in the header, footer, and page titles. "Career Platform" appears only when no profile is published. The visual system lives in DESIGN.md.

## Evidence on Hand

- `app/seed.py` and `app/fallback_profile.json` hold Greg's own public profile: his LinkedIn headline, a summary he approved, 7 roles, 4 skills, and 2 degrees. There are no projects and no GitHub link.
- Target roles are deliberately left empty. The site is public, and Greg doesn't want colleagues to read it as a job search, so no page should present him as open to new roles.
- `tests/seed_samples.py` holds the fictional "Alex Parker" sample that tests use when they need a full set of content. It must never ship as site content.
- The local `data/resume.db` holds the same profile and isn't committed.
- `data/Profile.pdf` is a local source document and is gitignored.
- There are no testimonials, client logos, press mentions, headshots, or verified outcome metrics. Future work must not invent any of them.

## Product Principles

1. Lead with value, then show the evidence. The home page answers "what does this person do for a business" before it lists anything.
2. Every claim on the page comes from a published database record. Templates hold structure, never resume content.
3. Absence is handled quietly. A missing optional field, an empty section, or a database outage removes elements cleanly instead of showing gaps or errors.
4. Context beats labels. A skill, metric, or role should appear next to the situation that gives it meaning.
5. The build stays simple enough for a student to read, run, and deploy to Railway.

## Accessibility & Inclusion

Each page has one `h1` and semantic headings below it. Navigation works by keyboard with a visible focus state, link text is descriptive rather than a bare URL, and color contrast is sufficient. A skip link goes to the main content. Mobile layouts must read without horizontal scrolling. The README's manual accessibility smoke checks are the release bar for content updates.
