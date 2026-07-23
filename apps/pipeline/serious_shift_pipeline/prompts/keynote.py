"""
Prompt builder for the keynote generator (steps/generate_keynote).

One narrative section per Key Trend. `evidence_text` is produced by the step's
format_evidence() (it needs the stored proponents/skeptics parser); this builder
only assembles the request from the shared template.
"""
from ._loader import load_and_render
from .voice import VOICE

KEYNOTE_MODEL = "claude-sonnet-4-6"


def keynote_section_prompt(kt: dict, evidence_text: str) -> str:
    return load_and_render(
        "keynote/section.txt",
        voice=VOICE,
        kt_name=kt['name'],
        kt_subtitle=kt['subtitle'],
        domain_name=kt['domain_name'],
        evidence=evidence_text,
    )
