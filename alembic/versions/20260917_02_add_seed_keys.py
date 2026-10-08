"""add stable seed keys

Revision ID: 20260917_02
Revises: 20260915_01
Create Date: 2026-09-17 22:01:05.233000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260917_02"
down_revision: str | Sequence[str] | None = "20260915_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("profiles", "skills", "experiences", "projects", "education"):
        op.add_column(
            table_name,
            sa.Column("seed_key", sa.String(length=255), nullable=True),
        )

    op.execute(
        "UPDATE profiles SET seed_key = 'profile:primary' "
        "WHERE seed_key IS NULL AND email = 'alex.parker@example.com'"
    )
    op.execute(
        "UPDATE skills SET seed_key = 'skill:sql' "
        "WHERE seed_key IS NULL AND name = 'SQL' AND category = 'analytics'"
    )
    op.execute(
        "UPDATE skills SET seed_key = 'skill:python' "
        "WHERE seed_key IS NULL AND name = 'Python' AND category = 'programming'"
    )
    op.execute(
        "UPDATE experiences SET "
        "seed_key = 'experience:west-coast-commerce:analytics-engineering-intern' "
        "WHERE seed_key IS NULL "
        "AND role_title = 'Analytics Engineering Intern' "
        "AND organization = 'West Coast Commerce' "
        "AND start_date = '2026-06-01'"
    )
    op.execute(
        "UPDATE projects SET seed_key = 'project:career-platform' "
        "WHERE seed_key IS NULL AND slug = 'career-platform'"
    )
    op.execute(
        "UPDATE education SET "
        "seed_key = 'education:california-state-university:information-systems-bs' "
        "WHERE seed_key IS NULL "
        "AND institution_name = 'California State University' "
        "AND degree_or_program = 'B.S.' "
        "AND start_date = '2022-08-22'"
    )

    # Bound booleans render as 1 and 0 on SQLite and true and false on PostgreSQL,
    # which rejects a boolean column compared to an integer.
    op.execute(
        sa.text(
            """
            UPDATE profiles
            SET published = :unpublished
            WHERE published = :published
              AND id != (
                  SELECT id
                  FROM profiles
                  WHERE published = :published
                  ORDER BY
                      CASE WHEN seed_key = 'profile:primary' THEN 0 ELSE 1 END,
                      id
                  LIMIT 1
              )
            """
        ).bindparams(
            sa.bindparam("unpublished", False, type_=sa.Boolean()),
            sa.bindparam("published", True, type_=sa.Boolean()),
        )
    )

    op.create_index("ux_profiles_seed_key", "profiles", ["seed_key"], unique=True)
    op.create_index(
        "ux_profiles_single_published",
        "profiles",
        ["published"],
        unique=True,
        sqlite_where=sa.text("published = 1"),
        postgresql_where=sa.text("published = true"),
    )
    op.create_index("ux_skills_seed_key", "skills", ["seed_key"], unique=True)
    op.create_index("ux_experiences_seed_key", "experiences", ["seed_key"], unique=True)
    op.create_index("ux_projects_seed_key", "projects", ["seed_key"], unique=True)
    op.create_index("ux_education_seed_key", "education", ["seed_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_education_seed_key", table_name="education")
    op.drop_index("ux_projects_seed_key", table_name="projects")
    op.drop_index("ux_experiences_seed_key", table_name="experiences")
    op.drop_index("ux_skills_seed_key", table_name="skills")
    op.drop_index("ux_profiles_single_published", table_name="profiles")
    op.drop_index("ux_profiles_seed_key", table_name="profiles")

    for table_name in ("education", "projects", "experiences", "skills", "profiles"):
        op.drop_column(table_name, "seed_key")
