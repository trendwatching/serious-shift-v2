"""Phase 3 — generate each domain's Key Trends.

Domains run SEQUENTIALLY, threading an accumulated `taken` name ledger, so the
four calls cannot mint near-twins of each other — the same advisory-ledger
pattern phase 4 uses for sub-trend names. The count is a range
(MIN_KTS_PER_DOM–MAX_KTS_PER_DOM): the old floor-only ask ("prefer more trends
over fewer") produced 51 shifts telling ~30 distinct stories. Overshoot is
truncated deterministically here so the publication gate's kt_count check is a
backstop, not a tripwire; a short response gets a bounded retry (there was
none — only a warning that scrolled past).
"""
from __future__ import annotations

from ...core.text import url_slug as slugify
from ...prompts import MAX_KTS_PER_DOM, MIN_KTS_PER_DOM, prompt_domain_key_trends
from ...prompts import fmt_claims_block  # noqa: F401  (kept for prompt helpers)
from ..config import DOMAINS
from ..dbutil import _slugger
from ..llm import generate_json

#: One re-ask for a domain that came back under MIN. Bounded: a second short
#: answer publishes short and the kt_count gate decides.
MAX_KT_ATTEMPTS = 2


def _valid_kts(result: object) -> list[dict]:
    raw = result.get('key_trends') if isinstance(result, dict) else None
    if not isinstance(raw, list):
        return []
    return [kt for kt in raw
            if isinstance(kt, dict) and kt.get('name') and kt.get('subtitle')]


def phase3_key_trends(conn, api_key: str, domain_claims: dict) -> dict:
    """
    Returns {domain_id: [kt_dict_with_db_id, ...]}
    Writes MIN..MAX_KTS_PER_DOM Key Trends per domain to domain_key_trends.
    """
    print('\nPhase 3 — Generating Key Trends per domain (sequential, shared name ledger)…')

    slug = _slugger()
    domain_kts: dict = {}
    taken: list[str] = []
    for d in DOMAINS:
        claims = domain_claims[d['id']]
        kts: list[dict] = []
        for attempt in range(1, MAX_KT_ATTEMPTS + 1):
            [result] = generate_json(
                [d],
                lambda dom: prompt_domain_key_trends(dom, claims, taken=taken),
                default=lambda: {'key_trends': []},
                describe=lambda dom: f"{dom['name']} (attempt {attempt})",
            )
            kts = _valid_kts(result)
            if len(kts) >= MIN_KTS_PER_DOM:
                break
            if attempt < MAX_KT_ATTEMPTS:
                print(f'  {d["name"]}: only {len(kts)} KTs '
                      f'(target {MIN_KTS_PER_DOM}–{MAX_KTS_PER_DOM}) — re-asking')
        if len(kts) < MIN_KTS_PER_DOM:
            print(f'  {d["name"]}: only {len(kts)} KTs after {MAX_KT_ATTEMPTS} '
                  f'attempts — the kt_count gate will decide')
        # Deterministic truncation past MAX: the model lists its strongest
        # candidates first, and a sixth-through-Nth thin trend is exactly what
        # the range exists to prevent.
        kts = kts[:MAX_KTS_PER_DOM]

        written = []
        for j, kt in enumerate(kts, start=1):
            kt['_db_id'] = conn.execute("""
                INSERT INTO domain_key_trends
                  (slug, domain_id, name, subtitle, velocity, sort_order)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
            """, (slug(f'kt-{slugify(kt["name"])}'), d['id'],
                  kt['name'], kt.get('subtitle', ''), kt.get('velocity', 'rising'), j)).fetchone()['id']
            kt['_claim_ids'] = [int(cid) for cid in kt.get('claim_ids', [])
                                if isinstance(cid, (int, float)) and not isinstance(cid, bool)]
            written.append(kt)
            taken.append(str(kt['name']))
        domain_kts[d['id']] = written
        print(f'  ✓  {d["name"]}: {len(written)} KTs')

    conn.commit()
    return domain_kts
