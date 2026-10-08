import importlib
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.models.experience import Experience, ExperienceAccomplishment
from app.models.profile import Profile
from app.models.project import Project
from app.models.skill import Skill


def _reload_session_module(
    monkeypatch, database_url: str = "sqlite+pysqlite:///:memory:"
):
    monkeypatch.setenv("DATABASE_URL", database_url)

    session_module = importlib.import_module("app.db.session")
    return importlib.reload(session_module)


def test_project_skill_association_persists_across_sessions(monkeypatch) -> None:
    session_module = _reload_session_module(monkeypatch)
    Base.metadata.create_all(session_module.engine)

    with session_module.SessionLocal() as session:
        project = Project(
            slug="revenue-dashboard",
            title="Revenue Dashboard",
            summary="Dashboard for weekly sales decisions.",
            problem="Sales reporting was delayed.",
            contribution="Built the reporting model.",
            methods="SQL and Python",
            published=True,
        )
        skill = Skill(name="Python", category="backend", published=True)

        project.skills.append(skill)

        session.add(project)
        session.commit()
        project_id = project.id

    with session_module.SessionLocal() as session:
        reloaded_project = session.execute(
            select(Project).where(Project.id == project_id)
        ).scalar_one()
        association_count = session.execute(
            text("SELECT COUNT(*) FROM project_skills WHERE project_id = :project_id"),
            {"project_id": project_id},
        ).scalar_one()

        assert [saved_skill.name for saved_skill in reloaded_project.skills] == [
            "Python"
        ]
        assert association_count == 1


def test_session_local_enables_sqlite_foreign_keys(monkeypatch) -> None:
    session_module = _reload_session_module(monkeypatch)

    with session_module.SessionLocal() as session:
        foreign_keys = session.execute(text("PRAGMA foreign_keys")).scalar_one()

    assert foreign_keys == 1


def test_database_delete_cascades_experience_accomplishments(monkeypatch) -> None:
    session_module = _reload_session_module(monkeypatch)
    Base.metadata.create_all(session_module.engine)

    with session_module.SessionLocal() as session:
        experience = Experience(
            role_title="Business Analyst Intern",
            organization="Acme Corp",
            location="Los Angeles, CA",
            start_date=date(2025, 6, 1),
            end_date=date(2025, 8, 31),
            is_current=False,
            summary="Supported reporting improvements.",
            published=True,
        )
        experience.accomplishments.append(
            ExperienceAccomplishment(
                statement="Reduced manual reporting effort.",
                metric="4 hours per week",
            )
        )

        session.add(experience)
        session.commit()
        experience_id = experience.id
        accomplishment_id = experience.accomplishments[0].id

        session.execute(
            text("DELETE FROM experiences WHERE id = :experience_id"),
            {"experience_id": experience_id},
        )
        session.commit()

        remaining_accomplishments = session.execute(
            text(
                "SELECT COUNT(*) FROM experience_accomplishments "
                "WHERE id = :accomplishment_id"
            ),
            {"accomplishment_id": accomplishment_id},
        ).scalar_one()

        assert remaining_accomplishments == 0


def test_database_allows_only_one_published_profile(monkeypatch) -> None:
    session_module = _reload_session_module(monkeypatch)
    Base.metadata.create_all(session_module.engine)

    with session_module.SessionLocal() as session:
        session.add(
            Profile(
                full_name="First Candidate",
                headline="First public profile",
                summary="First profile summary.",
                location="Los Angeles, CA",
                target_roles="Analytics Engineer",
                email="first@example.com",
                published=True,
            )
        )
        session.commit()
        session.add(
            Profile(
                full_name="Second Candidate",
                headline="Second public profile",
                summary="Second profile summary.",
                location="Los Angeles, CA",
                target_roles="Analytics Engineer",
                email="second@example.com",
                published=True,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_single_published_profile_index_is_partial_on_both_databases() -> None:
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateIndex

    index = next(
        index
        for index in Profile.__table__.indexes
        if index.name == "ux_profiles_single_published"
    )

    sqlite_ddl = str(CreateIndex(index).compile(dialect=sqlite.dialect()))
    postgres_ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "WHERE published = 1" in sqlite_ddl
    assert "WHERE published = true" in postgres_ddl
