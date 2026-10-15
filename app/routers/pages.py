from __future__ import annotations

import hashlib
from collections import OrderedDict
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.urls import normalize_http_url
from app.services import DatabaseUnavailableError, ResumeService
from app.services.contact import (
    CONTACT_FIELD_LIMITS,
    clean_contact_values,
    validate_contact,
)
from app.services.resume import role_note
from app.services.timeline import build_timeline, experience_anchor

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates"
)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _static_version() -> str:
    """Short content hash so browsers fetch fresh CSS and JS after each deploy."""
    digest = hashlib.sha256()
    for name in ("styles.css", "timeline.js"):
        digest.update((STATIC_DIR / name).read_bytes())
    return digest.hexdigest()[:10]


templates.env.globals["safe_http_url"] = normalize_http_url
templates.env.globals["static_version"] = _static_version()
templates.env.globals["experience_anchor"] = experience_anchor
GENERIC_OUTAGE_MESSAGE = (
    "This service is temporarily unavailable. Please try again later."
)


def get_resume_service(request: Request) -> ResumeService:
    return ResumeService(request.app.state.session_factory)


ResumeServiceDependency = Annotated[ResumeService, Depends(get_resume_service)]


def _navigation(
    request: Request, *, include_resume_pages: bool = True
) -> list[dict[str, str | bool]]:
    items = [
        {
            "label": "Home",
            "href": str(request.url_for("homepage")),
            "current": request.url.path == "/",
        },
    ]
    if include_resume_pages:
        items.extend(
            [
                {
                    "label": "Experience",
                    "href": str(request.url_for("experience_page")),
                    "current": request.url.path == "/experience",
                },
                {
                    "label": "Projects",
                    "href": str(request.url_for("projects_page")),
                    "current": request.url.path.startswith("/projects"),
                },
                {
                    "label": "Skills",
                    "href": str(request.url_for("skills_page")),
                    "current": request.url.path == "/skills",
                },
                {
                    "label": "Education",
                    "href": str(request.url_for("education_page")),
                    "current": request.url.path == "/education",
                },
            ]
        )
    items.append(
        {
            "label": "Contact",
            "href": str(request.url_for("contact_page")),
            "current": request.url.path == "/contact",
        }
    )
    return items


def _render(
    request: Request,
    template_name: str,
    context: dict,
    *,
    site_name: str,
    status_code: int = status.HTTP_200_OK,
    include_resume_pages: bool = True,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        template_name,
        {
            **context,
            "site_name": site_name,
            "nav_links": _navigation(
                request, include_resume_pages=include_resume_pages
            ),
        },
        status_code=status_code,
    )


def _service_unavailable(request: Request, service: ResumeService) -> HTMLResponse:
    return _render(
        request,
        "error.html",
        {"message": GENERIC_OUTAGE_MESSAGE},
        site_name=service.get_site_name(),
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        include_resume_pages=False,
    )


def _not_found(request: Request, service: ResumeService) -> HTMLResponse:
    return _render(
        request,
        "not_found.html",
        {},
        site_name=service.get_site_name(),
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _group_skills(skills: list[Any]) -> list[tuple[str, list[Any]]]:
    grouped: OrderedDict[str, list[Any]] = OrderedDict()
    for skill in skills:
        grouped.setdefault(skill.category, []).append(skill)
    return list(grouped.items())


@router.get("/", response_class=HTMLResponse, name="homepage")
def homepage(
    request: Request,
    service: ResumeServiceDependency,
) -> HTMLResponse:
    homepage_content = service.get_homepage()
    profile = homepage_content.profile
    promoted = {highlight.statement for highlight in homepage_content.highlights}
    selected_roles = [
        (experience, note)
        for experience in homepage_content.experiences
        if (note := role_note(experience, promoted))
    ]
    return _render(
        request,
        "home.html",
        {
            "content": homepage_content,
            "timeline": build_timeline(homepage_content.all_experiences),
            "skill_groups": _group_skills(homepage_content.skills),
            "selected_roles": selected_roles,
        },
        site_name=profile.full_name if profile else service.get_site_name(),
        include_resume_pages=not homepage_content.is_fallback,
    )


@router.get("/experience", response_class=HTMLResponse, name="experience_page")
def experience_page(
    request: Request,
    service: ResumeServiceDependency,
) -> HTMLResponse:
    try:
        experiences = service.get_experiences()
    except DatabaseUnavailableError:
        return _service_unavailable(request, service)

    return _render(
        request,
        "experience.html",
        {
            "experiences": experiences,
            "timeline": build_timeline(experiences),
        },
        site_name=service.get_site_name(),
    )


@router.get("/projects", response_class=HTMLResponse, name="projects_page")
def projects_page(
    request: Request,
    service: ResumeServiceDependency,
) -> HTMLResponse:
    try:
        projects = service.get_projects()
    except DatabaseUnavailableError:
        return _service_unavailable(request, service)

    return _render(
        request,
        "projects.html",
        {"projects": projects},
        site_name=service.get_site_name(),
    )


@router.get("/projects/{slug}", response_class=HTMLResponse, name="project_detail")
def project_detail(
    slug: str,
    request: Request,
    service: ResumeServiceDependency,
) -> HTMLResponse:
    try:
        project = service.get_project_by_slug(slug)
    except DatabaseUnavailableError:
        return _service_unavailable(request, service)

    if project is None:
        return _not_found(request, service)

    return _render(
        request,
        "project_detail.html",
        {"project": project},
        site_name=service.get_site_name(),
    )


@router.get("/skills", response_class=HTMLResponse, name="skills_page")
def skills_page(
    request: Request,
    service: ResumeServiceDependency,
) -> HTMLResponse:
    try:
        skills = service.get_skills()
    except DatabaseUnavailableError:
        return _service_unavailable(request, service)

    return _render(
        request,
        "skills.html",
        {"skill_groups": _group_skills(skills)},
        site_name=service.get_site_name(),
    )


@router.get("/education", response_class=HTMLResponse, name="education_page")
def education_page(
    request: Request,
    service: ResumeServiceDependency,
) -> HTMLResponse:
    try:
        education = service.get_education()
    except DatabaseUnavailableError:
        return _service_unavailable(request, service)

    return _render(
        request,
        "education.html",
        {"education_records": education},
        site_name=service.get_site_name(),
    )


@router.get("/privacy", response_class=HTMLResponse, name="privacy_page")
def privacy_page(request: Request, service: ResumeServiceDependency) -> HTMLResponse:
    return _render(request, "privacy.html", {}, site_name=service.get_site_name())


@router.get("/contact", response_class=HTMLResponse, name="contact_page")
def contact_page(request: Request, service: ResumeServiceDependency) -> HTMLResponse:
    return _render(
        request,
        "contact.html",
        {"values": {}, "errors": {}, "limits": CONTACT_FIELD_LIMITS},
        site_name=service.get_site_name(),
    )


@router.post("/contact", response_class=HTMLResponse, name="contact_submit")
def contact_submit(
    request: Request,
    service: ResumeServiceDependency,
    name: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    message: Annotated[str, Form()] = "",
) -> HTMLResponse:
    # Submissions are shown back to the sender only. Nothing is stored or emailed yet.
    values = clean_contact_values(name, email, message)
    errors = validate_contact(values)
    if errors:
        return _render(
            request,
            "contact.html",
            {"values": values, "errors": errors, "limits": CONTACT_FIELD_LIMITS},
            site_name=service.get_site_name(),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return _render(
        request,
        "contact_received.html",
        {"values": values},
        site_name=service.get_site_name(),
    )
