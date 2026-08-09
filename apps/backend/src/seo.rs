//! Per-page metadata, robots.txt and sitemap.xml, derived from the map document.
//!
//! The frontend is a static export: every route is served the same `index.html`,
//! so all 347 pages shared one `<title>`, one description, no Open Graph tags
//! and no canonical. Crawlers and link unfurlers saw one page; `robots.txt` and
//! `sitemap.xml` did not exist and the SPA fallback answered them with HTML.
//!
//! It is done here rather than at build time because the frontend build has no
//! database access — and doing it here means the metadata tracks the current map
//! instead of whatever was true when the image was built. The backend already
//! holds the document in memory, so this costs a lookup.

use std::collections::HashMap;

use serde_json::Value;

/// Title and description for one route.
#[derive(Clone, Debug, PartialEq)]
pub struct PageMeta {
    pub title: String,
    pub description: String,
    /// The link-preview card, when this route has one of its own.
    ///
    /// Every route shared one generic logo card, so a shift posted into Slack
    /// previewed as "the site" rather than as itself. A shift's card is drawn
    /// from the same seed as its hero (`scripts/render-og.mjs`), and a
    /// sub-shift inherits its parent's — exactly as the hero already does.
    /// `None` falls back to the generic card, which is right for `/`, `/about`
    /// and the spheres, none of which are a single subject.
    pub image: Option<String>,
}

/// Every canonical route in the map, with its metadata.
#[derive(Debug, Default)]
pub struct SiteIndex {
    pub pages: HashMap<String, PageMeta>,
    /// Canonical routes, in document order — the sitemap's contents.
    pub routes: Vec<String>,
    /// `updated` from the document, used as the sitemap's lastmod.
    pub updated: String,
}

/// The wordmark in running text. NOT "Shi(f)t" — the parenthetical is a device
/// that belongs to the logo alone, and this string is prose: it is the browser
/// tab, the Slack unfurl, the search result. The logo lock-up in `og.png` and
/// the two header/footer images keep the "(f)" because they are the logo.
const SITE_NAME: &str = "Serious Shift";
/// Descriptions longer than this are cut at a word boundary. Search engines
/// truncate around 155-160 characters; a sentence cut mid-word reads as broken.
const MAX_DESC: usize = 155;

/// A trend name as the house style writes it: caps, in double quotation marks.
///
/// The page has always done the caps in CSS, which is presentational only — it
/// never reaches the `<title>`, the OG card, or anything a reader copies. So a
/// shift shared into WhatsApp unfurled as `Delegated Discovery` while the page
/// it linked to said `DELEGATED DISCOVERY`. This is the one place that can fix
/// it server-side, and `useDocumentMeta.js` applies the identical rule on the
/// client so the title does not change under hydration.
///
/// Strip first, then re-apply: the naming prompt shows its examples already
/// quoted (`packages/prompts/map/key_trends.txt`), so a name occasionally
/// arrives carrying a pair of its own. Stripping makes this idempotent.
fn trend_title(name: &str) -> String {
    let bare = name
        .trim()
        .trim_matches(|c| matches!(c, '\u{201C}' | '\u{201D}' | '"' | '\'' | ' '))
        .trim();
    if bare.is_empty() {
        return String::new();
    }
    format!("\u{201C}{}\u{201D}", bare.to_uppercase())
}

fn s(v: &Value, k: &str) -> String {
    v.get(k)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_string()
}

/// Trim to `MAX_DESC` on a word boundary, adding an ellipsis when cut.
fn clamp(text: &str) -> String {
    let t: String = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if t.chars().count() <= MAX_DESC {
        return t;
    }
    let cut: String = t.chars().take(MAX_DESC).collect();
    let head = cut.rsplit_once(' ').map(|(a, _)| a).unwrap_or(&cut);
    format!("{}…", head.trim_end_matches([',', ';', ':', '-', '.']))
}

/// Build the route index from the raw map document.
///
/// Slugs are taken from the document, never re-derived: `key_trends[].slug` and
/// `sub_trends[].slug` are already the path segments the frontend routes on
/// (a sub-trend's slug carries its parent, e.g. `parent-shift/this-one`).
/// Re-implementing the slug rule here would be a third copy to keep in step.
pub fn build_index(doc: &str) -> SiteIndex {
    let Ok(v) = serde_json::from_str::<Value>(doc) else {
        return SiteIndex::default();
    };
    let mut idx = SiteIndex {
        updated: s(&v, "updated"),
        ..Default::default()
    };

    let arr = |k: &str| -> Vec<Value> {
        v.get(k)
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default()
    };

    let domains = arr("domains");
    let shift_count = arr("key_trends").len();
    idx.add(
        "/".into(),
        PageMeta {
            image: None,
            title: format!("{SITE_NAME} — Everything that is about to change"),
            description: clamp(&format!(
                "{} domains and {} shifts in the current weekly map, told as stories. \
                 What is about to change, and who is saying so.",
                domains.len(),
                shift_count
            )),
        },
    );

    // The one route that is not a projection of the map document. It is still
    // registered here, because the index is also what decides whether `spa`
    // answers 200 or 404 — an authored page missing from it is served as a soft
    // 404, which is what /about did before this line existed.
    idx.add(
        "/about".into(),
        PageMeta {
            image: None,
            title: format!("About — {SITE_NAME}"),
            description: "Why Serious Shift exists, how we build it, and who is behind it. \
                          Powered by TrendWatching."
                .into(),
        },
    );

    for d in &domains {
        let id = s(d, "id");
        if id.is_empty() {
            continue;
        }
        let name = s(d, "name");
        let desc = {
            let short = s(d, "short_description");
            if short.is_empty() {
                s(d, "description")
            } else {
                short
            }
        };
        idx.add(
            format!("/{id}"),
            PageMeta {
                image: None,
                title: format!("{name} — {SITE_NAME}"),
                description: clamp(&desc),
            },
        );
    }

    for kt in arr("key_trends") {
        let (domain, slug, name) = (s(&kt, "domain_id"), s(&kt, "slug"), s(&kt, "name"));
        if domain.is_empty() || slug.is_empty() {
            continue;
        }
        idx.add(
            format!("/{domain}/{slug}"),
            PageMeta {
                image: Some(format!("/shift/og/{slug}.jpg")),
                title: format!("{} — {SITE_NAME}", trend_title(&name)),
                description: clamp(&s(&kt, "subtitle")),
            },
        );
    }

    for st in arr("sub_trends") {
        let (domain, slug, name) = (s(&st, "domain_id"), s(&st, "slug"), s(&st, "name"));
        if domain.is_empty() || slug.is_empty() {
            continue;
        }
        let desc = {
            let d = s(&st, "description");
            if d.is_empty() {
                s(&st, "subtitle")
            } else {
                d
            }
        };
        idx.add(
            format!("/{domain}/{slug}"),
            PageMeta {
                // A sub-shift's slug carries its parent, so the parent segment
                // is the card — the same inheritance the hero art uses.
                image: slug
                    .split('/')
                    .next()
                    .filter(|parent| !parent.is_empty())
                    .map(|parent| format!("/shift/og/{parent}.jpg")),
                title: format!("{} — {SITE_NAME}", trend_title(&name)),
                description: clamp(&desc),
            },
        );
    }
    idx
}

impl SiteIndex {
    fn add(&mut self, route: String, meta: PageMeta) {
        if self.pages.insert(route.clone(), meta).is_none() {
            self.routes.push(route);
        }
    }

    /// `<sitemap>` XML for every route, or None when the index is empty.
    pub fn sitemap(&self, origin: &str) -> String {
        let lastmod = if self.updated.is_empty() {
            String::new()
        } else {
            format!("<lastmod>{}</lastmod>", self.updated)
        };
        let urls: String = self
            .routes
            .iter()
            .map(|r| {
                format!(
                    "<url><loc>{}{}</loc>{}</url>",
                    origin,
                    xml_escape(r),
                    lastmod
                )
            })
            .collect();
        format!(
            r#"<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>"#
        )
    }
}

pub fn robots(origin: &str) -> String {
    // Deliberately open: this is a public publication. The only thing worth
    // keeping crawlers out of is the JSON API, which is not content.
    format!("User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: {origin}/sitemap.xml\n")
}

fn xml_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn attr_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

/// Rewrite the exported shell's `<head>` for one route.
///
/// Replaces the build-time title and description and appends canonical, Open
/// Graph and Twitter tags. Everything else in the shell — the hashed script
/// tags especially — is left exactly as Next emitted it.
pub fn render(shell: &str, route: &str, meta: &PageMeta, origin: &str) -> String {
    let title = attr_escape(&meta.title);
    let desc = attr_escape(&meta.description);
    let url = format!("{}{}", origin, route);

    let mut out = replace_between(shell, "<title>", "</title>", &title);
    out = replace_meta_description(&out, &desc);

    let extra = format!(
        concat!(
            r#"<link rel="canonical" href="{url}"/>"#,
            r#"<meta property="og:type" content="website"/>"#,
            r#"<meta property="og:site_name" content="{site}"/>"#,
            r#"<meta property="og:title" content="{title}"/>"#,
            r#"<meta property="og:description" content="{desc}"/>"#,
            r#"<meta property="og:url" content="{url}"/>"#,
            r#"<meta property="og:image" content="{origin}{image}"/>"#,
            r#"<meta name="twitter:card" content="summary_large_image"/>"#,
            r#"<meta name="twitter:title" content="{title}"/>"#,
            r#"<meta name="twitter:description" content="{desc}"/>"#,
            r#"<meta name="twitter:image" content="{origin}{image}"/>"#,
        ),
        url = attr_escape(&url),
        site = SITE_NAME,
        title = title,
        desc = desc,
        origin = attr_escape(origin),
        image = attr_escape(meta.image.as_deref().unwrap_or("/og.png")),
    );

    match out.find("</head>") {
        Some(i) => {
            out.insert_str(i, &extra);
            out
        }
        None => out,
    }
}

/// Rewrite the shell for a genuine 404 without advertising the invalid URL as
/// canonical or generating a share preview for it.
pub fn render_not_found(shell: &str) -> String {
    let mut out = replace_between(
        shell,
        "<title>",
        "</title>",
        "Page not found · Serious Shift",
    );
    out = replace_meta_description(
        &out,
        "This address is not part of the current Serious Shift map.",
    );
    match out.find("</head>") {
        Some(i) => {
            out.insert_str(i, r#"<meta name="robots" content="noindex, nofollow"/>"#);
            out
        }
        None => out,
    }
}

fn replace_between(hay: &str, open: &str, close: &str, with: &str) -> String {
    let Some(a) = hay.find(open) else {
        return hay.to_string();
    };
    let from = a + open.len();
    let Some(rel) = hay[from..].find(close) else {
        return hay.to_string();
    };
    let mut out = String::with_capacity(hay.len() + with.len());
    out.push_str(&hay[..from]);
    out.push_str(with);
    out.push_str(&hay[from + rel..]);
    out
}

/// Swap the content of the build-time `<meta name="description">`, whatever
/// attribute order Next emitted it in.
fn replace_meta_description(hay: &str, desc: &str) -> String {
    let Some(start) = hay.find(r#"<meta name="description""#) else {
        return hay.to_string();
    };
    let Some(rel_end) = hay[start..].find("/>") else {
        return hay.to_string();
    };
    let end = start + rel_end + 2;
    let mut out = String::with_capacity(hay.len());
    out.push_str(&hay[..start]);
    out.push_str(&format!(r#"<meta name="description" content="{desc}"/>"#));
    out.push_str(&hay[end..]);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const DOC: &str = r#"{
      "updated": "2026-08-01",
      "domains": [{"id":"society","name":"Society","short_description":"How AGI rewrites the social contract."}],
      "key_trends": [{"domain_id":"society","slug":"sovereign-collapse","name":"Sovereign Collapse","subtitle":"Private AI companies now hold national-security-equivalent capabilities."}],
      "sub_trends": [{"domain_id":"society","slug":"sovereign-collapse/threshold-blindness","name":"Threshold Blindness","description":"Nobody agrees where the line is."}]
    }"#;

    const SHELL: &str = r#"<!DOCTYPE html><html><head><meta charSet="utf-8"/><title>Old Title</title><meta name="description" content="Four domains, eight shifts this week."/></head><body>x</body></html>"#;

    /// A trend name reaches the tab and the unfurl in the house style, and a
    /// sphere name does not. The distinction is the whole point: `Society` is a
    /// section of the site, `"SOVEREIGN COLLAPSE"` is the name of a trend.
    #[test]
    fn trend_titles_are_capsed_and_quoted_but_spheres_are_not() {
        let idx = build_index(DOC);
        assert_eq!(
            idx.pages["/society/sovereign-collapse"].title,
            "\u{201C}SOVEREIGN COLLAPSE\u{201D} — Serious Shift"
        );
        assert_eq!(
            idx.pages["/society/sovereign-collapse/threshold-blindness"].title,
            "\u{201C}THRESHOLD BLINDNESS\u{201D} — Serious Shift"
        );
        assert_eq!(idx.pages["/society"].title, "Society — Serious Shift");
        assert_eq!(idx.pages["/about"].title, "About — Serious Shift");
    }

    /// A shift previews as ITSELF, and a sub-shift as its parent.
    ///
    /// Every one of the ~347 routes stamped the same generic logo card, so a
    /// shift shared into Slack or WhatsApp looked like the site rather than
    /// like the thing that was shared. The card is drawn from the same seed as
    /// the shift's hero. `/`, `/about` and the spheres keep the generic one —
    /// none of them is a single subject.
    #[test]
    fn a_shift_previews_as_itself_and_a_sub_shift_as_its_parent() {
        let idx = build_index(DOC);
        assert_eq!(
            idx.pages["/society/sovereign-collapse"].image.as_deref(),
            Some("/shift/og/sovereign-collapse.jpg")
        );
        assert_eq!(
            idx.pages["/society/sovereign-collapse/threshold-blindness"]
                .image
                .as_deref(),
            Some("/shift/og/sovereign-collapse.jpg")
        );
        assert_eq!(idx.pages["/society"].image, None);
        assert_eq!(idx.pages["/about"].image, None);
        assert_eq!(idx.pages["/"].image, None);

        // …and the fallback is the generic card, not an empty attribute.
        let out = render(SHELL, "/", &idx.pages["/"], "https://x.test");
        assert!(out.contains(r#"<meta property="og:image" content="https://x.test/og.png"/>"#));
        let shift = render(
            SHELL,
            "/society/sovereign-collapse",
            &idx.pages["/society/sovereign-collapse"],
            "https://x.test",
        );
        assert!(shift.contains(
            r#"<meta name="twitter:image" content="https://x.test/shift/og/sovereign-collapse.jpg"/>"#
        ));
    }

    /// Idempotent, because the naming prompt shows its examples already quoted
    /// and a name occasionally arrives carrying its own pair. Quoting a quoted
    /// name would ship `““NAME””`.
    #[test]
    fn trend_title_strips_whatever_quoting_it_arrived_with() {
        assert_eq!(
            trend_title("Delegated Discovery"),
            "\u{201C}DELEGATED DISCOVERY\u{201D}"
        );
        assert_eq!(
            trend_title("\"Delegated Discovery\""),
            "\u{201C}DELEGATED DISCOVERY\u{201D}"
        );
        assert_eq!(
            trend_title("\u{201C}Delegated Discovery\u{201D}"),
            "\u{201C}DELEGATED DISCOVERY\u{201D}"
        );
        assert_eq!(trend_title("   "), "");
        assert_eq!(trend_title(""), "");
    }

    /// Renders the REAL shipped shell, not a fixture.
    ///
    /// `render` swaps the first title tag in the document. If the shell ever
    /// carries that literal inside an HTML comment, the swap lands there, the
    /// comment never closes, and every tag after it — script and stylesheet
    /// included — is swallowed into the comment. The page then ships as a
    /// valid-looking 200 that renders absolutely nothing, which is exactly
    /// what happened once.
    #[test]
    fn rendering_the_real_shell_keeps_the_bundle_reachable() {
        // The BUILT shell, not the source one. Vite hoists the entry script
        // from <body> into <head> during the build, so the source file cannot
        // tell us whether a head rewrite would swallow it.
        let mut path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let shell_path = loop {
            let candidate = path.join("apps/frontend/out/index.html");
            if candidate.is_file() {
                break candidate;
            }
            if !path.pop() {
                return; // frontend not built in this checkout
            }
        };
        let shell = std::fs::read_to_string(shell_path).unwrap();
        let meta = PageMeta {
            title: "T".into(),
            description: "D".into(),
            image: None,
        };
        let out = render(&shell, "/", &meta, "https://example.com");

        assert!(
            out.contains("<div id=\"root\""),
            "the mount point must survive"
        );
        let head = out.split("<body").next().unwrap();
        assert!(
            head.contains("<script") && head.contains("/assets/"),
            "the entry script must survive the head rewrite: {head}",
        );
        // Every comment that opens must close before the body starts.
        assert_eq!(
            head.matches("<!--").count(),
            head.matches("-->").count(),
            "an unclosed comment in <head> swallows everything after it",
        );
    }

    /// `/about` is authored, not generated, so nothing in the map document
    /// would ever put it in the index — and a route missing from the index is
    /// served as a soft 404 with the shell, which is what it was.
    #[test]
    fn the_about_page_is_indexed_and_not_a_soft_404() {
        let idx = build_index(DOC);
        let meta = idx.pages.get("/about").expect("/about must be indexed");
        assert!(meta.title.starts_with("About"));
        assert!(!meta.description.is_empty());
    }

    #[test]
    fn every_level_of_the_route_tree_gets_metadata() {
        let idx = build_index(DOC);
        for r in [
            "/",
            "/society",
            "/society/sovereign-collapse",
            "/society/sovereign-collapse/threshold-blindness",
        ] {
            assert!(idx.pages.contains_key(r), "missing {r}");
        }
    }

    #[test]
    fn titles_are_distinct_per_page() {
        // The defect this replaces: 347 pages sharing one title.
        let idx = build_index(DOC);
        let titles: std::collections::HashSet<_> = idx.pages.values().map(|m| &m.title).collect();
        assert_eq!(titles.len(), idx.pages.len());
    }

    #[test]
    fn homepage_counts_come_from_the_document() {
        // Not "eight shifts this week", which was hard-coded and wrong.
        let idx = build_index(DOC);
        let d = &idx.pages["/"].description;
        assert!(d.contains("1 domains") && d.contains("1 shifts"), "{d}");
    }

    #[test]
    fn descriptions_are_clamped_on_a_word_boundary() {
        let long = "word ".repeat(100);
        let out = clamp(&long);
        assert!(out.chars().count() <= MAX_DESC + 1);
        assert!(out.ends_with('…'));
        assert!(!out.contains("  "));
    }

    #[test]
    fn short_descriptions_are_untouched() {
        assert_eq!(clamp("A short one."), "A short one.");
    }

    #[test]
    fn render_replaces_title_and_description() {
        let idx = build_index(DOC);
        let out = render(SHELL, "/society", &idx.pages["/society"], "https://x.test");
        assert!(out.contains("<title>Society — Serious Shift</title>"));
        assert!(!out.contains("Old Title"));
        assert!(out.contains("How AGI rewrites the social contract."));
        assert!(!out.contains("eight shifts this week"));
    }

    #[test]
    fn render_adds_canonical_and_social_tags() {
        let idx = build_index(DOC);
        let out = render(SHELL, "/society", &idx.pages["/society"], "https://x.test");
        assert!(out.contains(r#"<link rel="canonical" href="https://x.test/society"/>"#));
        assert!(out.contains(r#"<meta property="og:title""#));
        assert!(out.contains(r#"<meta name="twitter:card" content="summary_large_image"/>"#));
    }

    #[test]
    fn render_leaves_the_script_tags_alone() {
        let shell = r#"<html><head><title>t</title><script src="/_next/static/chunks/a.js"></script></head><body></body></html>"#;
        let meta = PageMeta {
            title: "T".into(),
            description: "D".into(),
            image: None,
        };
        let out = render(shell, "/", &meta, "https://x.test");
        assert!(out.contains(r#"<script src="/_next/static/chunks/a.js"></script>"#));
    }

    #[test]
    fn quotes_in_content_cannot_break_out_of_an_attribute() {
        let meta = PageMeta {
            title: r#"He said "hi" & <b>left</b>"#.into(),
            description: r#"a "quoted" phrase"#.into(),
            // A path is attribute-escaped like everything else, so a slug that
            // somehow carried a quote could not break out of og:image either.
            image: Some(r#"/shift/og/a"b.jpg"#.into()),
        };
        let out = render(SHELL, "/", &meta, "https://x.test");
        assert!(out.contains("&quot;hi&quot;"));
        assert!(out.contains("&lt;b&gt;"));
        assert!(out.contains(r#"content="https://x.test/shift/og/a&quot;b.jpg""#));
        assert!(!out.contains(r#"content="a "quoted""#));
    }

    #[test]
    fn sitemap_lists_every_route_with_lastmod() {
        let idx = build_index(DOC);
        let xml = idx.sitemap("https://x.test");
        assert_eq!(xml.matches("<url>").count(), idx.routes.len());
        assert!(xml.contains("<loc>https://x.test/society</loc>"));
        assert!(xml.contains("<lastmod>2026-08-01</lastmod>"));
    }

    #[test]
    fn robots_points_at_the_sitemap_and_excludes_the_api() {
        let r = robots("https://x.test");
        assert!(r.contains("Sitemap: https://x.test/sitemap.xml"));
        assert!(r.contains("Disallow: /api/"));
    }

    #[test]
    fn a_malformed_document_yields_an_empty_index_rather_than_panicking() {
        let idx = build_index("not json");
        assert!(idx.pages.is_empty() && idx.routes.is_empty());
    }

    #[test]
    fn entries_without_a_slug_are_skipped_not_rendered_as_bare_paths() {
        let doc = r#"{"domains":[],"key_trends":[{"domain_id":"society","name":"No Slug"}],"sub_trends":[]}"#;
        let idx = build_index(doc);
        assert!(idx.routes.iter().all(|r| r != "/society/"));
    }

    #[test]
    fn not_found_metadata_replaces_the_build_defaults_and_is_not_canonical() {
        let out = render_not_found(SHELL);
        assert!(out.contains("<title>Page not found · Serious Shift</title>"));
        assert!(out.contains(r#"content="noindex, nofollow""#));
        assert!(!out.contains("canonical"));
        assert!(!out.contains("Old Title"));
    }
}
