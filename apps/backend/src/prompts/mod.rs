//! Shared prompt text, vendored from `packages/prompts` (the single source of
//! truth) by `scripts/sync_prompts.py` and embedded at compile time with
//! `include_str!` — so the slim runtime image needs no prompt files on disk.
//!
//! This is the same `voice.txt` the Python pipeline loads, so the voice stays
//! identical across the whole application. Templates use `{{name}}` placeholders.

/// Serious Shift tone of voice — identical text to the Python pipeline's VOICE.
pub const VOICE: &str = include_str!("voice.txt");

const REWRITE_SECTION: &str = include_str!("personalize/rewrite_section.txt");

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
