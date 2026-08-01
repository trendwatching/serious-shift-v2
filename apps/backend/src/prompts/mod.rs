//! Shared prompt text read straight from `packages/prompts` — the single source
//! of truth — and embedded at compile time with `include_str!`, so the slim
//! runtime image needs no prompt files on disk.
//!
//! Reading the canonical path directly means there is no vendored copy to drift:
//! editing `packages/prompts/voice.txt` recompiles this crate. It does require
//! `packages/` to be present at build time, which the repo-root Docker build
//! context guarantees.
//!
//! This is the same `voice.txt` the Python pipeline loads, so the voice stays
//! identical across the whole application. Templates use `{{name}}` placeholders.

/// Serious Shift tone of voice — identical text to the Python pipeline's VOICE.
pub const VOICE: &str = include_str!("../../../../packages/prompts/voice.txt");

const REWRITE_SECTION: &str =
    include_str!("../../../../packages/prompts/personalize/rewrite_section.txt");

/// Replace each `{{key}}` in `template` with its value.
fn render(template: &str, vars: &[(&str, &str)]) -> String {
    let mut out = template.to_string();
    for (k, v) in vars {
        out = out.replace(&format!("{{{{{k}}}}}"), v);
    }
    out
}

/// Build the `/api/personalize` prompt that rewrites one keynote section for an
/// industry, in the shared Serious Shift voice.
pub fn rewrite_section(industry: &str, body: &str) -> String {
    render(
        REWRITE_SECTION,
        &[
            ("voice", VOICE.trim_end()),
            ("industry", industry),
            ("body", body),
        ],
    )
}
