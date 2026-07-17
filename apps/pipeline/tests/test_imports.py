"""Import-smoke test: every module imports cleanly (catches syntax/name errors).
The Anthropic SDK is imported lazily, so even the LLM-backed modules import
without it installed."""


def test_all_modules_import():
    # core
    import serious_shift_pipeline.core.config  # noqa: F401
    import serious_shift_pipeline.core.db  # noqa: F401
    import serious_shift_pipeline.core.llm  # noqa: F401
    import serious_shift_pipeline.core.migrate  # noqa: F401
    import serious_shift_pipeline.core.observability  # noqa: F401
    import serious_shift_pipeline.core.parallel  # noqa: F401
    import serious_shift_pipeline.core.voice  # noqa: F401
    # steps
    import serious_shift_pipeline.steps.scraper  # noqa: F401
    import serious_shift_pipeline.steps.process_raw  # noqa: F401
    import serious_shift_pipeline.steps.scoring  # noqa: F401
    import serious_shift_pipeline.steps.generate_map_data  # noqa: F401
    import serious_shift_pipeline.steps.generate_keynote  # noqa: F401
    import serious_shift_pipeline.steps.evaluate  # noqa: F401
    import serious_shift_pipeline.steps.deduplicate  # noqa: F401
    # tools
    import serious_shift_pipeline.tools.ingest  # noqa: F401
    import serious_shift_pipeline.tools.status  # noqa: F401
    import serious_shift_pipeline.tools.queries  # noqa: F401
    # orchestrator
    import serious_shift_pipeline.run_weekly  # noqa: F401
