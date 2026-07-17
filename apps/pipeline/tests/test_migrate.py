"""DB-free tests for the migration applier's parsing helpers, run against the
real packages/db migrations so they stay in sync with the dbmate version scheme."""
import os

from serious_shift_pipeline.core import migrate


def test_version_matches_dbmate_scheme():
    # dbmate records the leading digits of the filename as the version.
    assert migrate._version("0001_initial_schema.sql") == "0001"
    assert migrate._version("0005_drop_scenario_layer.sql") == "0005"


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


def test_vendored_migrations_match_canonical():
    """The package's vendored migrations must stay byte-identical to the
    canonical packages/db/migrations (the dbmate source of truth)."""
    repo = migrate._REPO_MIGRATIONS
    if not repo or not repo.is_dir():
        import pytest
        pytest.skip("canonical packages/db/migrations not present (installed/sdist build)")
    pkg = migrate._PKG_MIGRATIONS
    repo_files = sorted(f.name for f in repo.glob("*.sql"))
    pkg_files = sorted(f.name for f in pkg.glob("*.sql"))
    assert pkg_files == repo_files, "vendored migration set differs from packages/db"
    for name in repo_files:
        assert (pkg / name).read_text() == (repo / name).read_text(), \
            f"{name}: vendored copy drifted from packages/db — re-copy it"


def test_repo_migrations_are_discoverable_and_parse():
    mdir = migrate._migrations_dir()
    assert mdir and os.path.isdir(mdir)
    files = sorted(f for f in os.listdir(mdir) if f.endswith(".sql"))
    assert files, "no migration files found"
    versions = [migrate._version(f) for f in files]
    assert len(versions) == len(set(versions)), "duplicate migration versions"
    for f in files:
        up = migrate._up_sql(open(os.path.join(mdir, f)).read())
        assert up, f"{f}: empty up-section"
