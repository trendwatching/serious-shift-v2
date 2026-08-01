"""
Domain-first trend-map generation.

The map is built in numbered phases, each an independent fan-out of Claude calls
over one unit of work (a domain, a Key Trend), followed by a serial DB write.
`pipeline.run_all` sequences them; `export.build_map_json_v2` assembles the
single document the frontend reads.

Split out of a 1700-line single module. The seams are the phase
boundaries that were already marked by comment banners in that file — nothing was
rewritten in the move, and tests/test_map_export_golden.py pins the exported
document so a regression in `export` is caught rather than shipped.

Entry point: `python -m serious_shift_pipeline.mapgen.cli`
"""
from .config import (
    CLAIMS_PER_DOM, CLAIMS_PER_KT, DOMAINS, MIN_KTS_PER_DOM, MODULE_ORDER,
)

__all__ = ["CLAIMS_PER_DOM", "CLAIMS_PER_KT", "DOMAINS", "MIN_KTS_PER_DOM", "MODULE_ORDER"]
