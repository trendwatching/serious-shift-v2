#!/usr/bin/env python3
"""
status.py — back-of-house dashboard for the pipeline (Postgres).

Read-only snapshot: recent runs, DB stats, source status, errors, cost,
migrations. Everything comes from Postgres — run history moved off the
container filesystem, where it did not survive the job that wrote it.

Usage:  DATABASE_URL=... python -m serious_shift_pipeline.tools.status
"""
import os
from datetime import datetime, timezone

from ..core import db, observability

RAW_CONTENT = os.environ.get("RAW_CONTENT_DIR", os.path.join(os.getcwd(), "raw_content"))


def _age_str(ts_iso: str | None) -> str:
    if not ts_iso:
        return "unknown"
    try:
        dt = datetime.fromisoformat(ts_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = int((datetime.now(timezone.utc) - dt).total_seconds())
        if secs < 0:
            return "just now"
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return ts_iso


def _masked_dsn() -> str:
    dsn = os.environ.get("DATABASE_URL", "")
    return dsn.split("@")[-1] if "@" in dsn else (dsn or "DATABASE_URL not set")


def collect_status(raw_content: str = RAW_CONTENT) -> dict:
    data: dict = {"runs": [], "last_run": {"timestamp": None, "age": "no runs yet"},
                  "errors": {"total_7d": 0, "by_step": []}}

    # ── DB stats / sources / migrations (single connection) ──────
    db_stats = {"total_claims": 0, "signal_claims": 0, "total_sources": 0,
                "total_thinkers": 0, "db_size": "Postgres", "db_path": _masked_dsn()}
    source_status = {"ok": 0, "partial": 0, "failed": 0, "total": 0}
    top_broken: list = []
    migrations = {"applied": 0, "total": 0, "pending": [], "version": None}
    try:
        with db.connect() as conn:
            db_stats["total_claims"] = db.scalar(conn, "SELECT COUNT(*) FROM claims")
            db_stats["signal_claims"] = db.scalar(conn,
                "SELECT COUNT(*) FROM claims WHERE signal_strength IN ('signal','strong_signal') AND duplicate_of IS NULL")
            db_stats["total_sources"] = db.scalar(conn, "SELECT COUNT(*) FROM sources")
            db_stats["total_thinkers"] = db.scalar(conn, "SELECT COUNT(*) FROM thinkers")

            for r in db.query(conn, "SELECT last_run_status AS s, COUNT(*) AS n FROM source_state GROUP BY last_run_status"):
                if r["s"] in source_status:
                    source_status[r["s"]] = r["n"]
            source_status["total"] = sum(source_status[k] for k in ("ok", "partial", "failed"))
            top_broken = [
                {"thinker": r["name"], "platform": r["platform"], "url": r["source_url"],
                 "last_fetched": r["last_fetched_at"]}
                for r in db.query(conn, """
                    SELECT t.name, s.platform, s.source_url, s.last_fetched_at
                    FROM source_state s JOIN thinkers t ON t.id = s.thinker_id
                    WHERE s.last_run_status = 'failed'
                    ORDER BY s.last_fetched_at DESC LIMIT 5""")
            ]

            # dbmate's bookkeeping table (version TEXT)
            try:
                vers = [r["version"] for r in db.query(conn, "SELECT version FROM schema_migrations ORDER BY version")]
                migrations = {"applied": len(vers), "total": len(vers), "pending": [],
                              "version": vers[-1] if vers else None}
            except Exception:
                migrations = {"error": "schema_migrations not found"}

            # ── Run history ──────────────────────────────────────
            data["runs"] = [
                {**r, "age": _age_str(r["started_at"].isoformat())}
                for r in observability.recent_runs(conn, limit=5)
            ]
            if data["runs"]:
                latest = data["runs"][0]
                data["last_run"] = {
                    "timestamp": latest["started_at"].isoformat(),
                    "age": latest["age"],
                }
            data["errors"] = {
                "total_7d": db.scalar(conn,
                    "SELECT COUNT(*) FROM pipeline_errors "
                    "WHERE occurred_at > now() - interval '7 days'"),
                "by_step": db.query(conn,
                    "SELECT step, COUNT(*) AS n FROM pipeline_errors "
                    "WHERE occurred_at > now() - interval '7 days' "
                    "GROUP BY step ORDER BY n DESC LIMIT 8"),
            }
    except Exception as exc:
        db_stats["error"] = str(exc)
    data["db"] = db_stats
    data["source_status"] = source_status
    data["top_broken"] = top_broken
    data["migrations"] = migrations

    # ── Raw content files ────────────────────────────────────────
    raw_txt_count = 0
    if os.path.isdir(raw_content):
        for _root, _dirs, files in os.walk(raw_content):
            raw_txt_count += sum(1 for f in files if f.endswith(".txt"))
    data["raw_files"] = {"count": raw_txt_count, "path": raw_content}

    return data


# ============================================================
# FORMATTING
# ============================================================

_SEP = "─" * 56
_THICK = "═" * 56


def format_status(data: dict) -> str:
    lines = []

    def h(title: str) -> None:
        lines.extend(["", _SEP, f"  {title}", _SEP])

    def row(label: str, value: str) -> None:
        lines.append(f"  {label:<26}{value}")

    lines.extend([_THICK, "  SERIOUS SHIFT — PIPELINE STATUS",
                  f'  {datetime.now().strftime("%Y-%m-%d %H:%M")}', _THICK])

    h("RECENT RUNS")
    runs = data.get("runs", [])
    if not runs:
        lines.append("  No runs recorded yet.")
    else:
        lines.append(f"  {'started':<14}{'stage':<12}{'status':<9}"
                     f"{'files':>6}{'claims':>9}{'cost':>9}")
        for r in runs:
            before, after = r["claims_before"], r["claims_after"]
            claims = f"{after - before:+,}" if before is not None and after is not None else "—"
            cost = f"${float(r['cost_usd']):.2f}"
            lines.append(
                f"  {r['age']:<14}{r['stage']:<12}{r['status']:<9}"
                f"{r['files_processed']:>6}{claims:>9}{cost:>9}"
            )

    h("DATABASE")
    dbd = data.get("db", {})
    if "error" in dbd:
        lines.append(f"  ERROR: {dbd['error']}")
    else:
        row("Total claims:", str(dbd.get("total_claims", 0)))
        row("Signal claims:", str(dbd.get("signal_claims", 0)) + "  (signal + strong_signal, non-dup)")
        row("Total sources:", str(dbd.get("total_sources", 0)))
        row("Thinkers:", str(dbd.get("total_thinkers", 0)))
        row("Database:", dbd.get("db_path", "?"))

    h("SOURCES BY STATUS")
    ss = data.get("source_status", {})
    row("OK:", str(ss.get("ok", 0)))
    row("Partial:", str(ss.get("partial", 0)))
    row("Failed:", str(ss.get("failed", 0)))
    row("Total tracked:", str(ss.get("total", 0)))
    broken = data.get("top_broken", [])
    if broken:
        lines.append("\n  Top failed sources:")
        for b in broken:
            lines.append(f"    {b['thinker']} / {b['platform']}")
            url = b["url"]
            lines.append(f"      {url[:47] + '...' if len(url) > 50 else url}")
    else:
        lines.append("  No failed sources.")

    h("RAW CONTENT")
    rf = data.get("raw_files", {})
    row("Scraped .txt files:", str(rf.get("count", 0)))
    row("Directory:", rf.get("path", "?"))

    h("ERRORS (LAST 7 DAYS)")
    errs = data.get("errors", {})
    row("Total:", str(errs.get("total_7d", 0)))
    for e in errs.get("by_step", []):
        row(f"  {e['step']}:", str(e["n"]))
    if errs.get("total_7d"):
        lines.append("\n  Detail: SELECT * FROM pipeline_errors ORDER BY occurred_at DESC;")

    h("MIGRATIONS")
    mg = data.get("migrations", {})
    if "error" in mg:
        lines.append(f"  {mg['error']}")
    else:
        row("Schema version:", str(mg.get("version")) if mg.get("version") is not None else "none")
        row("Applied:", f"{mg.get('applied', 0)}/{mg.get('total', 0)}")
        lines.append("  All migrations applied." if not mg.get("pending") else f"  Pending: {len(mg['pending'])}")

    lines.extend(["", _THICK])
    return "\n".join(lines)


def main() -> None:
    print(format_status(collect_status()))


if __name__ == "__main__":
    main()
