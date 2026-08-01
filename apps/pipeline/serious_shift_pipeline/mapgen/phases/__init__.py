"""One module per generation phase. Each writes its own rows and returns only
what the next phase needs, so a phase can be re-run in isolation."""
