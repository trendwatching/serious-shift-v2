"""Import-smoke test: every module imports cleanly (catches syntax/name errors).
The Anthropic SDK is imported lazily, so even the LLM-backed modules import
without it installed.

Keep this list complete. It is hand-maintained, and what it guards against is a
module that exists on a developer's disk but never reached git: the pipeline
image is built from the checkout, so a missing file is not a test failure but a
cron that dies at import every week. `mapgen.publish_hook` was exactly that —
imported by `mapgen.cli`, untracked, and absent from this list."""


def test_all_modules_import():
    # core
    import serious_shift_pipeline.core.config  # noqa: F401
    import serious_shift_pipeline.core.db  # noqa: F401
    import serious_shift_pipeline.core.llm  # noqa: F401
    import serious_shift_pipeline.core.migrate  # noqa: F401
    import serious_shift_pipeline.core.observability  # noqa: F401
    import serious_shift_pipeline.core.parallel  # noqa: F401
    # prompts (VOICE + every Claude prompt builder live here)
    import serious_shift_pipeline.prompts  # noqa: F401
    import serious_shift_pipeline.prompts.voice  # noqa: F401
    import serious_shift_pipeline.prompts.map_data  # noqa: F401
    import serious_shift_pipeline.prompts.extraction  # noqa: F401
    import serious_shift_pipeline.prompts.dedup  # noqa: F401
    import serious_shift_pipeline.prompts.ingest  # noqa: F401
    # steps
    import serious_shift_pipeline.steps.scraper  # noqa: F401
    import serious_shift_pipeline.steps.process_raw  # noqa: F401
    import serious_shift_pipeline.steps.scoring  # noqa: F401
    import serious_shift_pipeline.mapgen  # noqa: F401
    import serious_shift_pipeline.mapgen.cli  # noqa: F401
    import serious_shift_pipeline.mapgen.export  # noqa: F401
    import serious_shift_pipeline.mapgen.modules  # noqa: F401
    import serious_shift_pipeline.mapgen.parsers  # noqa: F401
    import serious_shift_pipeline.mapgen.publish_hook  # noqa: F401
    import serious_shift_pipeline.mapgen.routing  # noqa: F401
    import serious_shift_pipeline.mapgen.validation  # noqa: F401
    import serious_shift_pipeline.mapgen.config  # noqa: F401
    import serious_shift_pipeline.mapgen.phases.attribution  # noqa: F401
    import serious_shift_pipeline.mapgen.phases.domains  # noqa: F401
    import serious_shift_pipeline.mapgen.phases.editorial  # noqa: F401
    import serious_shift_pipeline.mapgen.phases.hero_stats  # noqa: F401
    import serious_shift_pipeline.mapgen.phases.interrelatedness  # noqa: F401
    import serious_shift_pipeline.mapgen.phases.key_trends  # noqa: F401
    import serious_shift_pipeline.mapgen.phases.routing  # noqa: F401
    import serious_shift_pipeline.mapgen.phases.sub_trends  # noqa: F401
    import serious_shift_pipeline.mapgen.phases.synthesis  # noqa: F401
    import serious_shift_pipeline.steps.evaluate  # noqa: F401
    import serious_shift_pipeline.steps.deduplicate  # noqa: F401
    # tools
    import serious_shift_pipeline.tools.ingest  # noqa: F401
    import serious_shift_pipeline.tools.status  # noqa: F401
    import serious_shift_pipeline.tools.queries  # noqa: F401
    # orchestrator
    import serious_shift_pipeline.run  # noqa: F401
