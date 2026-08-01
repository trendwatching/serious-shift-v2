"""DB-free tests for the migration applier's parsing helpers, run against the
real packages/db migrations so they stay in sync with the dbmate version scheme."""
import os
import re

from serious_shift_pipeline.core import migrate
from serious_shift_pipeline.paths import migrations_dir


def test_version_matches_dbmate_scheme():
    # dbmate records the leading digits of the filename as the version.
    assert migrate._version("20250101000000_baseline.sql") == "20250101000000"
    assert migrate._version("20260815091200_add_foo.sql") == "20260815091200"


def test_up_sql_excludes_down_section():
    sql = """-- migrate:up
CREATE TABLE foo (id int);
-- migrate:down
DROP TABLE foo;
"""
    up = migrate._up_sql(sql)
    assert "CREATE TABLE foo" in up
    assert "DROP TABLE foo" not in up
    assert "migrate:up" not in up


def test_migration_filenames_are_timestamped():
    """Migrations must use UTC-timestamp versions, not sequential counters.

    Sequential names (0001, 0002, …) collide whenever two branches add a
    migration, and the collision is silent — both files claim the same version,
    so one is never applied. A 14-digit timestamp cannot collide in practice.
    """
    for f in sorted(migrations_dir().glob("*.sql")):
        assert re.fullmatch(r"\d{14}_[a-z0-9_]+\.sql", f.name), (
            f"{f.name}: expected <YYYYMMDDHHMMSS>_<snake_case>.sql — "
            "generate with `dbmate new <name>`"
        )


def test_repo_migrations_are_discoverable_and_parse():
    mdir = migrations_dir()
    assert mdir.is_dir()
    files = sorted(f for f in os.listdir(mdir) if f.endswith(".sql"))
    assert files, "no migration files found"
    versions = [migrate._version(f) for f in files]
    assert len(versions) == len(set(versions)), "duplicate migration versions"
    for f in files:
        up = migrate._up_sql((mdir / f).read_text())
        assert up, f"{f}: empty up-section"
