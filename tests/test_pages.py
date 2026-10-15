from __future__ import annotations

from datetime import date
from html import unescape

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Education, Experience, ExperienceAccomplishment, Project, Skill
from app.schemas import (
    ContactLink,
    FallbackProfile,
    Highlight,
    HomepageContent,
    PublicProfile,
)
from app.services.resume import DatabaseUnavailableError


def fallback_homepage_content() -> HomepageContent:
    return HomepageContent(
        profile=FallbackProfile(
            full_name="Fallback Candidate",
            headline="Reliable analytics builder",
            summary="Supports business decisions with resilient systems.",
            location="Los Angeles, CA",
            target_roles=["Analytics Engineer"],
            contact_links=[
                ContactLink(
                    label="LinkedIn",
                    url="https://www.linkedin.com/in/fallback-candidate",
                )
            ],
        ),
        is_fallback=True,
        outage_message="Detailed resume information is temporarily unavailable.",
    )


def published_homepage_content() -> HomepageContent:
    sql_skill = Skill(
        name="SQL",
        category="analytics",
        context="Warehouse modeling and reporting.",
        display_order=1,
        published=True,
    )
    python_skill = Skill(
        name="Python",
        category="programming",
        context="Automation and service development.",
        display_order=2,
        published=True,
    )
    project = Project(
        slug="resume-site",
        title="Resume Site",
        summary="Public resume content from the database.",
        problem="Manual updates were slow.",
        contribution="Built the public rendering flow.",
        methods="FastAPI, SQLAlchemy, Jinja2",
        outcome="Faster content updates.",
        repository_url="https://github.com/example/resume-site",
        live_demo_url="https://resume.example.com",
        published=True,
        featured=True,
        display_order=1,
        skills=[sql_skill, python_skill],
    )
    experience = Experience(
        role_title="Analytics Engineer Intern",
        organization="North Star Co",
        location="Los Angeles, CA",
        start_date=date(2026, 1, 1),
        end_date=None,
        is_current=True,
        summary="Improved reporting operations.",
        published=True,
        display_order=1,
        skills=[sql_skill, python_skill],
    )
    experience.accomplishments = [
        ExperienceAccomplishment(
            statement="Automated weekly KPI reporting.",
            metric="6 hours saved weekly",
            display_order=1,
        )
    ]
    education = Education(
        institution_name="State University",
        degree_or_program="B.S.",
        field_of_study="Information Systems",
        start_date=date(2022, 8, 22),
        end_date=date(2026, 5, 18),
        gpa="3.8",
        honors="Dean's List",
        relevant_coursework=None,
        certifications=None,
        published=True,
        display_order=1,
    )

    return HomepageContent(
        profile=FallbackProfile(
            full_name="Alex Parker",
            headline="Analytics-focused software builder",
            summary="Builds dependable data products for business teams.",
            location="Los Angeles, CA",
            target_roles=["Analytics Engineer", "Data Analyst"],
            email="alex.parker@example.com",
            contact_links=[
                ContactLink(
                    label="LinkedIn",
                    url="https://www.linkedin.com/in/alexparker",
                ),
                ContactLink(
                    label="GitHub",
                    url="https://github.com/alexparker",
                ),
            ],
        ),
        experiences=[experience],
        all_experiences=[experience],
        experience_count=1,
        highlights=[
            Highlight(
                metric="6 hours saved weekly",
                statement="Automated weekly KPI reporting.",
                organization="North Star Co",
            )
        ],
        projects=[project],
        skills=[sql_skill, python_skill],
        education=[education],
        is_fallback=False,
    )


def test_homepage_renders_fallback_for_database_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_homepage",
        lambda _: fallback_homepage_content(),
    )

    with TestClient(create_app()) as app_client:
        response = app_client.get("/")

    assert response.status_code == 200
    assert "temporarily unavailable" in response.text
    assert 'id="home-impact-heading"' not in response.text
    assert "Experience" not in response.text


def test_homepage_renders_profile_navigation_and_featured_sections(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_homepage",
        lambda _: published_homepage_content(),
    )

    with TestClient(create_app()) as app_client:
        response = app_client.get("/")

    assert response.status_code == 200
    assert "Skip to main content" in response.text
    assert 'aria-label="Primary navigation"' in response.text
    assert (
        '<h1 id="page-title" class="action-title">'
        "Analytics-focused software builder</h1>" in response.text
    )
    assert '<p class="site-name"><a href="/">Alex Parker</a></p>' in response.text
    assert "Analytics-focused software builder" in response.text
    assert "Selected results" in response.text
    assert "6 hours saved weekly" in response.text
    assert (
        response.text.index("Analytics-focused software builder")
        < response.text.index('id="home-impact-heading"')
        < response.text.index('id="home-experience-heading"')
    )
    assert 'href="/experience"' in response.text
    assert 'href="/projects"' in response.text
    assert 'id="home-projects-heading"' in response.text
    assert "Resume Site" in response.text
    assert "State University" in response.text


def test_homepage_does_not_show_profile_email(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_homepage",
        lambda _: published_homepage_content(),
    )

    with TestClient(create_app()) as app_client:
        response = app_client.get("/")

    assert response.status_code == 200
    assert "alex.parker@example.com" not in response.text
    assert "mailto:" not in response.text


def test_experience_page_renders_experience_content(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_experiences",
        lambda _: published_homepage_content().experiences,
    )

    with TestClient(create_app()) as app_client:
        response = app_client.get("/experience")

    assert response.status_code == 200
    assert "<h1>Experience</h1>" in response.text
    assert "North Star Co" in response.text
    assert "Selected roles" not in response.text
    assert "Automated weekly KPI reporting." in response.text
    assert "6 hours saved weekly" in response.text
    assert "SQL" in response.text


def test_projects_pages_render_project_lists_and_external_links(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_projects",
        lambda _: published_homepage_content().projects,
    )
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_project_by_slug",
        lambda _, slug: (
            published_homepage_content().projects[0] if slug == "resume-site" else None
        ),
    )

    with TestClient(create_app()) as app_client:
        list_response = app_client.get("/projects")
        detail_response = app_client.get("/projects/resume-site")

    assert list_response.status_code == 200
    assert "<h1>Projects</h1>" in list_response.text
    assert 'href="/projects/resume-site"' in list_response.text
    assert detail_response.status_code == 200
    assert "<h1>Resume Site</h1>" in detail_response.text
    assert "Manual updates were slow." in detail_response.text
    assert 'target="_blank"' in detail_response.text
    assert 'rel="noopener noreferrer"' in detail_response.text


def test_project_detail_omits_unsafe_external_links(monkeypatch) -> None:
    project = published_homepage_content().projects[0]
    project.repository_url = "javascript:alert(1)"
    project.live_demo_url = "not a valid URL"
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_project_by_slug",
        lambda *_: project,
    )

    with TestClient(create_app()) as app_client:
        response = app_client.get("/projects/resume-site")

    assert response.status_code == 200
    assert 'aria-label="Project links"' not in response.text
    assert "javascript:" not in response.text
    assert "not a valid URL" not in response.text


def test_skills_and_education_pages_render_without_empty_optional_labels(
    monkeypatch,
) -> None:
    education = published_homepage_content().education[0]
    education.relevant_coursework = None
    education.certifications = None
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_skills",
        lambda _: published_homepage_content().skills,
    )
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_education",
        lambda _: [education],
    )

    with TestClient(create_app()) as app_client:
        skills_response = app_client.get("/skills")
        education_response = app_client.get("/education")

    assert skills_response.status_code == 200
    assert "<h1>Skills</h1>" in skills_response.text
    assert "Warehouse modeling and reporting." in skills_response.text
    assert education_response.status_code == 200
    assert "<h1>Education</h1>" in education_response.text
    assert "Dean's List" in unescape(education_response.text)
    assert "Relevant coursework" not in education_response.text
    assert "Certifications" not in education_response.text


def test_unknown_project_returns_not_found(client) -> None:
    response = client.get("/projects/no-such-project")

    assert response.status_code == 404
    assert "Page not found" in response.text


def test_unpublished_project_returns_not_found(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_project_by_slug",
        lambda *_: None,
    )

    with TestClient(create_app()) as app_client:
        response = app_client.get("/projects/no-such-project")

    assert response.status_code == 404
    assert "Page not found" in response.text


def test_non_homepage_database_failures_render_generic_503(monkeypatch) -> None:
    def raising(*_args, **_kwargs):
        raise DatabaseUnavailableError("Published data is unavailable")

    monkeypatch.setattr("app.services.resume.ResumeService.get_experiences", raising)
    monkeypatch.setattr("app.services.resume.ResumeService.get_projects", raising)
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_project_by_slug", raising
    )
    monkeypatch.setattr("app.services.resume.ResumeService.get_skills", raising)
    monkeypatch.setattr("app.services.resume.ResumeService.get_education", raising)

    with TestClient(create_app()) as app_client:
        responses = [
            app_client.get("/experience"),
            app_client.get("/projects"),
            app_client.get("/projects/resume-site"),
            app_client.get("/skills"),
            app_client.get("/education"),
        ]

    for response in responses:
        assert response.status_code == 503
        assert "Please try again later" in response.text
        assert "Published data is unavailable" not in response.text


def thin_homepage_content() -> HomepageContent:
    experience = published_homepage_content().experiences[0]
    experience.summary = ""
    experience.accomplishments = []
    return HomepageContent(
        profile=PublicProfile(
            full_name="Thin Candidate",
            headline="Professor of Analytics",
            summary="",
            location="Los Angeles, CA",
            target_roles=[],
            contact_links=[
                ContactLink(label="LinkedIn", url="https://www.linkedin.com/in/thin")
            ],
        ),
        experiences=[experience],
        all_experiences=[experience],
        experience_count=1,
        projects=[],
        skills=[],
        education=[],
    )


def test_homepage_omits_empty_fields_and_sections(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_homepage",
        lambda _: thin_homepage_content(),
    )

    with TestClient(create_app()) as app_client:
        response = app_client.get("/")

    assert response.status_code == 200
    assert "Thin Candidate" in response.text
    assert "Target roles" not in response.text
    assert "<p></p>" not in response.text.replace("\n", "").replace(" ", "")
    assert "<dd></dd>" not in response.text.replace("\n", "").replace(" ", "")
    assert 'id="home-projects-heading"' not in response.text
    assert 'id="home-skills-heading"' not in response.text
    assert 'id="home-education-heading"' not in response.text
    assert 'id="home-impact-heading"' not in response.text
    assert "North Star Co" in response.text


def test_detail_pages_omit_blank_optional_text(monkeypatch) -> None:
    content = published_homepage_content()
    experience = content.experiences[0]
    experience.summary = ""
    education = content.education[0]
    education.field_of_study = ""
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_experiences", lambda _: [experience]
    )
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_education", lambda _: [education]
    )
    monkeypatch.setattr("app.services.resume.ResumeService.get_projects", lambda _: [])

    with TestClient(create_app()) as app_client:
        experience_response = app_client.get("/experience")
        education_response = app_client.get("/education")
        projects_response = app_client.get("/projects")

    compact = experience_response.text.replace("\n", "").replace(" ", "")
    assert "<p></p>" not in compact
    assert "B.S. in" not in education_response.text
    assert "B.S." in education_response.text
    assert projects_response.status_code == 200
    assert "No projects are published yet." in projects_response.text


def test_static_assets_carry_a_content_version(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_homepage",
        lambda _: published_homepage_content(),
    )

    with TestClient(create_app()) as app_client:
        response = app_client.get("/")

    assert "styles.css?v=" in response.text
    assert "timeline.js?v=" in response.text


def test_homepage_copy_stays_plain(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_homepage",
        lambda _: published_homepage_content(),
    )

    with TestClient(create_app()) as app_client:
        response = app_client.get("/")

    for phrase in ("with results", "Next steps", "Reach ", "Source:", "every figure"):
        assert phrase.lower() not in response.text.lower()
    assert ">All experience</a>" in response.text


def test_every_page_loads_the_google_tag_exactly_once(monkeypatch) -> None:
    def raising(*_args, **_kwargs):
        raise DatabaseUnavailableError("Published data is unavailable")

    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_homepage",
        lambda _: fallback_homepage_content(),
    )
    monkeypatch.setattr("app.services.resume.ResumeService.get_experiences", raising)
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_project_by_slug", lambda *_: None
    )

    loader = "https://www.googletagmanager.com/gtag/js?id=G-QEYDY81QQ7"
    with TestClient(create_app()) as app_client:
        for path in ["/", "/experience", "/projects/missing", "/contact"]:
            html = app_client.get(path).text
            assert html.count(loader) == 1, path
            assert html.count("gtag('config', 'G-QEYDY81QQ7')") == 1, path
            assert html.index(loader) < html.index("<title>"), path


def test_privacy_page_renders_and_is_linked_from_every_footer(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.resume.ResumeService.get_homepage",
        lambda _: fallback_homepage_content(),
    )

    with TestClient(create_app()) as app_client:
        privacy = app_client.get("/privacy")
        home = app_client.get("/")
        contact = app_client.get("/contact")

    assert privacy.status_code == 200
    assert "<h1>Privacy</h1>" in privacy.text
    assert "G-QEYDY81QQ7" in privacy.text
    assert "_ga_QEYDY81QQ7" in privacy.text
    for page in (privacy, home, contact):
        assert page.text.count('href="http://testserver/privacy"') == 1
