"""Reading and writing shift_art / shift_art_briefs.

Art rows are committed as they are generated rather than held in one transaction
to the end. Generating ~250 images takes 10-25 minutes and a transaction open
that long blocks vacuum and risks the whole batch on one disconnect. Holding them
is also unnecessary: nothing can reach a row until `documents['map']` names it,
so an uncommitted-but-unreferenced row is invisible either way. The atomicity
that matters — art appearing at the same instant as the map — comes from the
single commit in `_write_map_document`, which is where the document and the
`last_published_at` stamp land together.
"""
from __future__ import annotations


def load_art(conn) -> dict[tuple[str, str, str], dict]:
    """Everything already generated, keyed (scope, slug, frame)."""
    rows = conn.execute(
        'SELECT scope, slug, frame, sha256, prompt_sha256, model FROM shift_art'
    ).fetchall()
    return {(r['scope'], r['slug'], r['frame']): dict(r) for r in rows}


def upsert_art(conn, rows: list[dict]) -> None:
    for row in rows:
        conn.execute("""
            INSERT INTO shift_art (scope, slug, frame, bytes, mime, width, height,
                                   byte_size, sha256, prompt_sha256, style, model)
            VALUES (%(scope)s, %(slug)s, %(frame)s, %(bytes)s, 'image/jpeg',
                    %(width)s, %(height)s, %(byte_size)s, %(sha256)s,
                    %(prompt_sha256)s, %(style)s, %(model)s)
            ON CONFLICT (scope, slug, frame) DO UPDATE SET
                bytes = EXCLUDED.bytes, width = EXCLUDED.width,
                height = EXCLUDED.height, byte_size = EXCLUDED.byte_size,
                sha256 = EXCLUDED.sha256, prompt_sha256 = EXCLUDED.prompt_sha256,
                style = EXCLUDED.style, model = EXCLUDED.model,
                generated_at = now()
        """, row)


def load_briefs(conn) -> dict[tuple[str, str], dict]:
    rows = conn.execute(
        'SELECT scope, slug, brief, input_sha256, model FROM shift_art_briefs'
    ).fetchall()
    return {(r['scope'], r['slug']): dict(r) for r in rows}


def upsert_briefs(conn, rows: list[dict]) -> None:
    for row in rows:
        conn.execute("""
            INSERT INTO shift_art_briefs (scope, slug, brief, input_sha256, model)
            VALUES (%(scope)s, %(slug)s, %(brief)s, %(input_sha256)s, %(model)s)
            ON CONFLICT (scope, slug) DO UPDATE SET
                brief = EXCLUDED.brief, input_sha256 = EXCLUDED.input_sha256,
                model = EXCLUDED.model, generated_at = now()
        """, row)


def publish_art(conn, live: set[tuple[str, str]]) -> int:
    """Stamp this publication onto the art it names, then drop the rest.

    `statement_timestamp()` rather than `now()`, for the reason
    `_publish_shift_refs` documents: `now()` is the transaction timestamp, so two
    publications inside one transaction would each look current to the other.

    Pruning is safe here in a way it is not for `shift_refs`: nothing links to
    art except the document being written in this same transaction, so a row no
    longer named is a row nothing can reach.
    """
    if not live:
        return 0
    # Two parallel arrays unnested into rows, NOT `(scope, slug) = ANY(%s)` with
    # a list of tuples: Postgres answers that with "input of anonymous composite
    # types is not implemented", and it would do so inside the publish
    # transaction — after every image had already been paid for.
    scopes = [scope for scope, _ in live]
    slugs = [slug for _, slug in live]
    pairs = 'SELECT * FROM unnest(%s::text[], %s::text[])'
    conn.execute(
        'UPDATE shift_art SET last_published_at = statement_timestamp() '
        f'WHERE (scope, slug) IN ({pairs})', (scopes, slugs))
    conn.execute(
        f'DELETE FROM shift_art WHERE (scope, slug) NOT IN ({pairs})', (scopes, slugs))
    removed = conn.execute(
        f'DELETE FROM shift_art_briefs WHERE (scope, slug) NOT IN ({pairs}) RETURNING 1',
        (scopes, slugs)).fetchall()
    return len(removed)
