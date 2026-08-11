# Keynote section prompt — archived (2026-08)

The keynote generation step (`packages/prompts/keynote/section.txt`,
`prompts/keynote.py`, `steps/generate_keynote.py`) was deleted on 2026-08-01 in
`35c449f` when the pipeline was split into ingest and synthesize. On 2026-08-05
the team posted an improved version of this prompt on the Miro board
("SERIOUS SHIFT 2026" → "Prompts to be updated" cluster), unaware the step no
longer exists. This file preserves that improved text so it is not lost if the
keynote step is ever reinstated. **No code loads this file.**

The improvement over the deleted version (three lines): the opener accepts a
named concrete action or falsifiable claim when no dated statistic exists —
instead of tempting the model to invent one — and the "so what" must be a
specific action or reframe.

```text
{{voice}}

Write one section of the Serious Shift keynote, in the voice above. Each section is
one Key Trend — a shift already underway that reshapes how people live and buy.

FORMAT
- 200-300 words MAXIMUM. 3-5 short paragraphs, none longer than 4 sentences.
- Open with the single most striking piece of evidence from the evidence below: a specific dated statistic, a named company's concrete action, or a falsifiable claim with a named source. Never open with context-setting or background.
- If no dated statistic is available, open with the sharpest named concrete claim and cite the thinker — do not invent a statistic or use a vague approximation.
- Every fact MUST come from the evidence below. Do not invent anything.
- If opposing camps are listed, name the disagreement — do not flatten it to consensus.
- Cite thinkers by last name only in the body.
- End the body with one concrete "so what" for a brand or consumer — a specific action or reframe, not a vague observation.
- After the body, add this EXACT line on its own paragraph (the one place scores appear):
Key thinkers: [every thinker you cited, each with their credibility score from the evidence, separated by middots]
Example: Key thinkers: Mollick (53.9) · Altman (52.8) · Hassabis (53.2)

Return ONLY the section body text followed by the Key thinkers line. No title. No preamble.

KEY TREND: {{kt_name}}
WHAT IT MEANS: {{kt_subtitle}}
DOMAIN: {{domain_name}}

EVIDENCE FROM DATABASE:
{{evidence}}
```
