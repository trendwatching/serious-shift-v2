#!/usr/bin/env python3
"""
status.py — back-of-house dashboard for the pipeline (Postgres).

Read-only snapshot: last run, DB stats, source status, logs, cost, migrations.
Converted from the legacy status.py: sqlite3 → db.py; the local `.db` file size
and the migrate.py-based migration check are replaced with a query of dbmate's
`schema_migrations` table.

Usage:  DATABASE_URL=... python -m serious_shift_pipeline.tools.status
"""
import json
import os
from datetime import datetime, timezone

from ..core import db

LOGS_DIR    = os.environ.get("SS_LOGS_DIR", os.path.join(os.getcwd(), "logs"))
ERROR_LOG   = os.path.join(LOGS_DIR, "error_log.jsonl")
TOKEN_LOG   = os.path.join(LOGS_DIR, "token_log.jsonl")
RAW_CONTENT = os.environ.get("RAW_CONTENT_DIR", os.path.join(os.getcwd(), "raw_content"))


def _read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


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


def _file_kb(path: str) -> str:
    return f"{os.path.getsize(path) / 1024:.1f} KB" if os.path.exists(path) else "not found"


def _masked_dsn() -> str:
    dsn = os.environ.get("DATABASE_URL", "")
    return dsn.split("@")[-1] if "@" in dsn else (dsn or "DATABASE_URL not set")


def collect_status(logs_dir: str = LOGS_DIR, raw_content: str = RAW_CONTENT) -> dict:
    error_log = os.path.join(logs_dir, "error_log.jsonl")
    token_log = os.path.join(logs_dir, "token_log.jsonl")
    data = {}

    # ── Last run ─────────────────────────────────────────────────
    token_entries = _read_jsonl(token_log)
    last_token = token_entries[-1] if token_entries else None
    last_run_at = last_token.get("run_at") if last_token else None
    error_entries = _read_jsonl(error_log)
    last_error_ts = error_entries[-1].get("timestamp") if error_entries else None
    if last_error_ts and (not last_run_at or last_error_ts > last_run_at):
        last_run_at = last_error_ts
    data["last_run"] = {"timestamp": last_run_at, "age": _age_str(last_run_at)}

    # ── DB stats / sources / migrations (single connection) ──────
    db_stats = {"total_claims": 0, "signal_claims": 0, "total_sources": 0,
                "total_thinkers": 0, "db_size": "Postgres", "db_path": _masked_dsn()}
    source_status = {"ok": 0, "partial": 0, "failed": 0, "total": 0}
    top_broken: list = []
    migrations = {"applied": 0, "total": 0, "pending": [], "version": None}
    try:
        with db.connect() as conn:
            db_stats["total_claims"] = db.query_one(conn, "SELECT COUNT(*) AS n FROM claims")["n"]
            db_stats["signal_claims"] = db.query_one(conn,
                "SELECT COUNT(*) AS n FROM claims WHERE signal_strength IN ('signal','strong_signal') AND duplicate_of IS NULL")["n"]
            db_stats["total_sources"] = db.query_one(conn, "SELECT COUNT(*) AS n FROM sources")["n"]
            db_stats["total_thinkers"] = db.query_one(conn, "SELECT COUNT(*) AS n FROM thinkers")["n"]

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

    # ── Log stats ────────────────────────────────────────────────
    now_ts = datetime.now(timezone.utc).timestamp()
    errors_7d = 0
    for e in error_entries:
        try:
            t = datetime.fromisoformat(e.get("timestamp", ""))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if (now_ts - t.timestamp()) <= 7 * 86400:
                errors_7d += 1
        except Exception:
            pass
    data["logs"] = {
        "error_log_size": _file_kb(error_log), "token_log_size": _file_kb(token_log),
        "total_errors": len(error_entries), "errors_7d": errors_7d,
    }

    # ── Last run cost ────────────────────────────────────────────
    if last_token:
        cost_rows = sorted(
            [(name, d.get("cost_usd", 0.0), d.get("calls", 0))
             for name, d in last_token.get("by_thinker", {}).items()],
            key=lambda x: -x[1])
        data["last_cost"] = {
            "total_usd": last_token.get("total_cost_usd", 0.0),
            "input_tokens": last_token.get("total_input_tokens", 0),
            "output_tokens": last_token.get("total_output_tokens", 0),
            "files_processed": last_token.get("total_files_processed", 0),
            "run_at": last_token.get("run_at", "?"), "by_thinker": cost_rows,
        }
    else:
        data["last_cost"] = None

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

    h("LAST RUN")
    lr = data.get("last_run", {})
    row("Timestamp:", lr.get("timestamp") or "no runs yet")
    row("Age:", lr.get("age", "—"))

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

    h("LOGS")
    lg = data.get("logs", {})
    row("error_log.jsonl:", lg.get("error_log_size", "?") + f"  ({lg.get('total_errors', 0)} total entries)")
    row("token_log.jsonl:", lg.get("token_log_size", "?"))
    row("Errors last 7d:", str(lg.get("errors_7d", 0)))

    h("LAST RUN COST")
    lc = data.get("last_cost")
    if not lc:
        lines.append("  No token log entries found.")
    else:
        row("Run at:", lc.get("run_at", "?"))
        row("Files processed:", str(lc.get("files_processed", 0)))
        row("Total cost:", f"${lc.get('total_usd', 0):.4f}")
        row("Tokens:", f"{lc.get('input_tokens', 0):,} in / {lc.get('output_tokens', 0):,} out")
        if lc.get("by_thinker"):
            lines.append("\n  By thinker:")
            for name, cost, calls in lc["by_thinker"]:
                lines.append(f"    {name:<22}  ${cost:.4f}  ({calls} call{'s' if calls != 1 else ''})")

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
