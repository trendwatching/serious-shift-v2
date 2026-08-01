# Pipeline image — the Railway cron service (and any container host).
#
# BUILD CONTEXT IS THE REPO ROOT, not apps/pipeline, so `packages/` can be
# copied in:  docker build -f apps/pipeline/Dockerfile .
#
# The orchestrator subprocesses `python -m serious_shift_pipeline.<step>`, so the
# package is installed into the image. Migrations, prompts and the module
# contract are read from /app/packages at runtime (see paths.py) — nothing is
# vendored into the package, so there is no copy to drift.
FROM python:3.13-slim
WORKDIR /app

# Dependencies first, from pyproject alone. Editing pipeline source then reuses
# this layer instead of reinstalling psycopg/yt-dlp/anthropic on every build.
COPY apps/pipeline/pyproject.toml ./
RUN python -c "import tomllib,sys; \
      sys.stdout.write('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" \
      > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt

COPY packages/ ./packages/
COPY apps/pipeline/serious_shift_pipeline ./serious_shift_pipeline
RUN pip install --no-cache-dir --no-deps .

# raw_content + logs are written under the working dir (ephemeral per run — fine,
# since scrape → process run in the same invocation; watermarks live in the DB).
CMD ["python", "-m", "serious_shift_pipeline.run", "all"]
