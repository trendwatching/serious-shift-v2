//! Which of a shift's generated modules the page actually shows.
//!
//! The pipeline generates every module the contract declares and publishes all of
//! them. The design build renders a subset, and that subset differs by sphere:
//! industries and territories are a Consumers-only section on a key shift, and
//! human_needs and territories are Consumers-only on a sub-shift. Several more
//! modules — pull_quote, tension_band, voices, related_shifts on key shifts;
//! signals, counter_signals, evidence on sub-shifts — are generated but rendered
//! nowhere yet.
//!
//! Two ways to express that, and the choice matters:
//!
//!  * stop generating them, or drop them at publication. Cheap, and wrong: the
//!    decision is editorial and reversible, and the cost of reversing it would be
//!    a full regeneration.
//!  * publish everything and filter on read. That is this module. `validate_map`
//!    still sees a complete document, so **hiding can never make a run
//!    unpublishable and un-hiding never needs a republication** — the flag is a
//!    row, and the change is live within `DOC_CACHE_TTL`.
//!
//! Three layers, most specific first: a `shift_module_visibility` row for
//! `(scope, domain, type)`, then one for `(scope, '*', type)`, then the contract
//! default mirrored below.
//!
//! One case skips the filter entirely: a page composed from a
//! `shift_module_overrides` row. An editor who hand-authored the whole module
//! list has already decided what appears, and a sphere-wide flag must not
//! silently delete a section they deliberately placed. `export.py` marks those
//! rows `authored`, and `build_snapshot` checks it.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;

use crate::innovations::{fnv1a, Scope};

/// The contract default, mirrored from `packages/contracts/shift_modules.json`.
///
/// Duplicated rather than read, for the same reason `MODULE_ORDER_*` is: the
/// backend image copies only `apps/backend/src` (see `apps/backend/Dockerfile`),
/// so `include_str!` of a path under `packages/` compiles locally and then fails
/// the Docker build. `default_visibility_matches_the_contract` reads the JSON and
/// fails if the two drift.
///
/// `organizations` — US spelling, the same everywhere since the sphere rename.
const DEFAULT_HIDDEN: [(&str, &str, &[&str]); 8] = [
    // Key shifts: the four modules the build never renders, plus the two that are
    // Consumers-only. The 11 Aug 2026 review also removed human_needs from the
    // Society and Economy key-shift pages.
    (
        "key_trend",
        "society",
        &[
            "pull_quote",
            "tension_band",
            "voices",
            "related_shifts",
            "industries",
            "territories",
            "human_needs",
        ],
    ),
    (
        "key_trend",
        "economy",
        &[
            "pull_quote",
            "tension_band",
            "voices",
            "related_shifts",
            "industries",
            "territories",
            "human_needs",
        ],
    ),
    (
        "key_trend",
        "organizations",
        &[
            "pull_quote",
            "tension_band",
            "voices",
            "related_shifts",
            "industries",
            "territories",
        ],
    ),
    (
        "key_trend",
        "consumers",
        &["pull_quote", "tension_band", "voices", "related_shifts"],
    ),
    // Sub-shifts: evidence never renders; human_needs and territories are
    // Consumers-only. signals and counter_signals were un-hidden everywhere by
    // the 11 Aug 2026 review.
    (
        "sub_trend",
        "society",
        &["evidence", "human_needs", "territories"],
    ),
    (
        "sub_trend",
        "economy",
        &["evidence", "human_needs", "territories"],
    ),
    (
        "sub_trend",
        "organizations",
        &["evidence", "human_needs", "territories"],
    ),
    ("sub_trend", "consumers", &["evidence"]),
];

/// Every explicit row, plus a hash of the query result.
///
/// Mirrors `innovations::Hydration`: the revision folds into the snapshot's cache
/// version so that flipping a flag changes every affected ETag immediately.
/// Without it a client holding `If-None-Match` keeps a page whose composition has
/// changed.
#[derive(Default)]
pub struct Policy {
    rows: BTreeMap<(String, String, String), bool>,
    pub revision: u64,
}

const ALL_ROWS: &str = "
    SELECT coalesce(json_agg(json_build_array(scope, domain_id, module_type, visible)
                             ORDER BY scope, domain_id, module_type), '[]'::json)::text
      FROM shift_module_visibility
";

/// Load the editor's deviations from the contract default, in one round trip.
///
/// Deliberately infallible, like `innovations::load`: a policy table that cannot
/// be read must not be an outage. The contract default is a complete, correct
/// answer on its own, so a failure logs and falls back to it.
pub async fn load(pool: &sqlx::PgPool) -> Policy {
    let raw: Result<String, _> = sqlx::query_scalar(ALL_ROWS).fetch_one(pool).await;
    let raw = match raw {
        Ok(raw) => raw,
        Err(error) => {
            tracing::warn!(%error, "module visibility load failed; using the contract default");
            return Policy::default();
        }
    };
    let revision = fnv1a(&raw);
    let parsed: Vec<(String, String, String, bool)> =
        serde_json::from_str(&raw).unwrap_or_else(|error| {
            tracing::warn!(%error, "module visibility returned unparseable JSON");
            Vec::new()
        });
    let rows = parsed
        .into_iter()
        .map(|(scope, domain, module_type, visible)| ((scope, domain, module_type), visible))
        .collect();
    Policy { rows, revision }
}

impl Policy {
    /// A policy that differs only in its revision, for asserting that the
    /// snapshot's cache version folds the revision in. Without that fold, an
    /// editor flips a flag and every client holding `If-None-Match` keeps the
    /// old composition until the publication timestamp moves — a week later.
    #[cfg(test)]
    pub(crate) fn with_revision(revision: u64) -> Self {
        Policy {
            rows: BTreeMap::new(),
            revision,
        }
    }

    /// Exact row beats wildcard row beats contract default.
    pub fn is_visible(&self, scope: Scope, domain: &str, module_type: &str) -> bool {
        let key = |d: &str| {
            (
                scope.as_str().to_string(),
                d.to_string(),
                module_type.to_string(),
            )
        };
        if let Some(&visible) = self.rows.get(&key(domain)) {
            return visible;
        }
        if let Some(&visible) = self.rows.get(&key("*")) {
            return visible;
        }
        !default_hidden(scope, domain).contains(module_type)
    }

    /// Drop every hidden module, preserving the order of the rest.
    ///
    /// Runs *after* `innovations::hydrate`, so hiding `innovations` for a sphere
    /// works: the module is inserted and then removed, rather than the two
    /// fighting over whether it exists.
    pub fn apply(&self, modules: &mut Vec<Value>, scope: Scope, domain: &str) {
        modules.retain(|module| {
            module
                .get("type")
                .and_then(Value::as_str)
                .is_none_or(|t| self.is_visible(scope, domain, t))
        });
    }
}

/// The default hidden set for a sphere. An unknown sphere hides nothing, which is
/// the safe direction: a new domain shows everything it generated rather than
/// silently rendering a blank page.
fn default_hidden(scope: Scope, domain: &str) -> BTreeSet<&'static str> {
    DEFAULT_HIDDEN
        .iter()
        .find(|(s, d, _)| *s == scope.as_str() && *d == domain)
        .map(|(_, _, hidden)| hidden.iter().copied().collect())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn module(type_: &str) -> Value {
        json!({ "type": type_, "data": {} })
    }

    fn types(modules: &[Value]) -> Vec<String> {
        modules
            .iter()
            .map(|m| m["type"].as_str().unwrap_or_default().to_string())
            .collect()
    }

    fn policy(rows: &[(&str, &str, &str, bool)]) -> Policy {
        Policy {
            rows: rows
                .iter()
                .map(|(s, d, t, v)| ((s.to_string(), d.to_string(), t.to_string()), *v))
                .collect(),
            revision: 0,
        }
    }

    /// The const above is a copy of the contract, because the backend image
    /// cannot read `packages/`. This is what stops the copy drifting.
    #[test]
    fn default_visibility_matches_the_contract() {
        let mut path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let contract = loop {
            let candidate = path.join("packages/contracts/shift_modules.json");
            if candidate.is_file() {
                break candidate;
            }
            if !path.pop() {
                // Installed/vendored checkout without the contracts package.
                return;
            }
        };
        let contract: Value =
            serde_json::from_str(&std::fs::read_to_string(contract).unwrap()).unwrap();
        for (scope, domain, ours) in DEFAULT_HIDDEN {
            let theirs: Vec<&str> = contract["visibility"]["hidden"][scope][domain]
                .as_array()
                .unwrap_or_else(|| panic!("contract has no visibility.hidden.{scope}.{domain}"))
                .iter()
                .map(|v| v.as_str().unwrap())
                .collect();
            assert_eq!(
                theirs.iter().copied().collect::<BTreeSet<_>>(),
                ours.iter().copied().collect::<BTreeSet<_>>(),
                "{scope}/{domain} visibility drifted from the contract",
            );
        }
        // And nothing in the contract is missing from the const.
        for scope in ["key_trend", "sub_trend"] {
            let domains = contract["visibility"]["hidden"][scope].as_object().unwrap();
            for domain in domains.keys() {
                assert!(
                    DEFAULT_HIDDEN
                        .iter()
                        .any(|(s, d, _)| *s == scope && d == domain),
                    "contract declares {scope}/{domain} but the const does not",
                );
            }
        }
    }

    #[test]
    fn the_contract_default_applies_with_no_rows() {
        let policy = Policy::default();
        // Consumers keeps industries and territories; nobody else does.
        assert!(policy.is_visible(Scope::KeyTrend, "consumers", "industries"));
        assert!(!policy.is_visible(Scope::KeyTrend, "society", "industries"));
        // human_needs left the Society and Economy key-shift pages in the
        // 11 Aug 2026 review but stays on Organizations and Consumers, and as a
        // sub-shift section only for Consumers. Easy to invert by accident.
        assert!(!policy.is_visible(Scope::KeyTrend, "society", "human_needs"));
        assert!(!policy.is_visible(Scope::KeyTrend, "economy", "human_needs"));
        assert!(policy.is_visible(Scope::KeyTrend, "organizations", "human_needs"));
        assert!(policy.is_visible(Scope::KeyTrend, "consumers", "human_needs"));
        assert!(!policy.is_visible(Scope::SubTrend, "society", "human_needs"));
        assert!(policy.is_visible(Scope::SubTrend, "consumers", "human_needs"));
        // signals/counter_signals came ON for every sub-shift in the same review.
        assert!(policy.is_visible(Scope::SubTrend, "society", "signals"));
        assert!(policy.is_visible(Scope::SubTrend, "economy", "counter_signals"));
        assert!(!policy.is_visible(Scope::SubTrend, "society", "evidence"));
    }

    #[test]
    fn an_explicit_row_beats_the_wildcard_beats_the_default() {
        let policy = policy(&[
            ("key_trend", "*", "voices", true),
            ("key_trend", "society", "voices", false),
        ]);
        // exact row wins
        assert!(!policy.is_visible(Scope::KeyTrend, "society", "voices"));
        // wildcard covers everyone else, overriding the default
        assert!(policy.is_visible(Scope::KeyTrend, "economy", "voices"));
        // and the default still governs a type no row mentions
        assert!(!policy.is_visible(Scope::KeyTrend, "economy", "pull_quote"));
    }

    #[test]
    fn apply_removes_hidden_modules_and_keeps_the_order() {
        let mut modules = vec![
            module("dek"),
            module("from_to"),
            module("pull_quote"),
            module("stat_band"),
            module("industries"),
            module("territories"),
            module("innovations"),
            module("sub_shift_list"),
        ];
        Policy::default().apply(&mut modules, Scope::KeyTrend, "society");
        assert_eq!(
            types(&modules),
            [
                "dek",
                "from_to",
                "stat_band",
                "innovations",
                "sub_shift_list"
            ],
        );
    }

    #[test]
    fn consumers_keeps_the_commercial_modules() {
        let mut modules = vec![module("industries"), module("territories")];
        Policy::default().apply(&mut modules, Scope::KeyTrend, "consumers");
        assert_eq!(types(&modules), ["industries", "territories"]);
    }

    /// Hiding `innovations` has to work even though the backend inserts that
    /// module itself. It does, because `apply` runs after `hydrate`.
    #[test]
    fn hiding_innovations_survives_hydration() {
        let mut modules = vec![module("dek")];
        crate::innovations::hydrate(
            &mut modules,
            Scope::KeyTrend,
            Some(&json!([{ "title": "An example" }])),
        );
        assert!(types(&modules).contains(&"innovations".to_string()));

        let policy = policy(&[("key_trend", "society", "innovations", false)]);
        policy.apply(&mut modules, Scope::KeyTrend, "society");
        assert!(!types(&modules).contains(&"innovations".to_string()));
    }

    /// An unknown module type is never dropped. The registry already renders a
    /// defensive fallback for one, and silently deleting it would hide the drift
    /// that the fallback exists to surface.
    #[test]
    fn an_unknown_type_is_left_alone() {
        let mut modules = vec![module("something_new")];
        Policy::default().apply(&mut modules, Scope::KeyTrend, "society");
        assert_eq!(types(&modules), ["something_new"]);
    }

    /// A sphere nobody has a rule for shows everything, rather than nothing.
    #[test]
    fn an_unknown_sphere_hides_nothing() {
        let mut modules = vec![module("pull_quote"), module("industries")];
        Policy::default().apply(&mut modules, Scope::KeyTrend, "a-new-domain");
        assert_eq!(types(&modules), ["pull_quote", "industries"]);
    }
}
