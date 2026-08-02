# Pipeline image — the Railway cron service (and any container host).
#
# BUILD CONTEXT IS THE REPO ROOT, not apps/pipeline, so `packages/` can be
# copied in:  docker build -f apps/pipeline/Dockerfile .
#
# The orchestrator subprocesses `python -m serious_shift_pipeline.<step>`, so the
# package is installed into the image. Migrations, prompts and the module
# contract are read from /app/packages at runtime (see paths.py) — nothing is
# vendored into the package, so there is no copy to drift.
FROM python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91
WORKDIR /app

# Dependencies are resolved and hash-locked outside the image. Editing pipeline
# source therefore reuses this layer, while an altered package artifact fails
# closed instead of being accepted by pip.
COPY apps/pipeline/pyproject.toml apps/pipeline/requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY packages/ ./packages/
COPY apps/pipeline/serious_shift_pipeline ./serious_shift_pipeline
RUN pip install --no-cache-dir --no-deps --no-build-isolation .

RUN groupadd --system --gid 10001 pipeline \
    && useradd --system --uid 10001 --gid pipeline --no-create-home pipeline \
    && chown -R pipeline:pipeline /app

# raw_content + logs are written under the working dir (ephemeral per run — fine,
# since scrape → process run in the same invocation; watermarks live in the DB).
USER 10001:10001
CMD ["python", "-m", "serious_shift_pipeline.run", "all"]
