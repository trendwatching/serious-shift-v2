# Backend image — serves the read API *and* the exported SPA from one process,
# so there is no second always-on service and no cross-origin hop.
#
# BUILD CONTEXT IS THE REPO ROOT:  docker build -f apps/backend/Dockerfile .
# The crate embeds packages/prompts via include_str!, and the runtime image
# carries apps/frontend's static export, so both must be in the context.
#
# The build stage mirrors the repo layout (/app/apps/backend + /app/packages)
# because include_str! paths are resolved relative to the source file.

# ── 1. Frontend: static export ───────────────────────────────────────────────
FROM node:22-slim AS web
WORKDIR /web
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci
COPY apps/frontend/ ./
RUN npm run build          # → /web/out

# ── 2. Backend: compile ──────────────────────────────────────────────────────
FROM rust:1-bookworm AS build
WORKDIR /app/apps/backend
# Dependencies first, against a stub main, so editing src/ doesn't recompile
# every crate in the tree — that is the bulk of the build time.
COPY apps/backend/Cargo.toml apps/backend/Cargo.lock ./
RUN mkdir src && echo 'fn main() {}' > src/main.rs \
    && cargo build --release \
    && rm -rf src
COPY packages/prompts /app/packages/prompts
COPY apps/backend/src ./src
# Touch so cargo doesn't reuse the stub's fingerprint for the real main.rs.
RUN touch src/main.rs && cargo build --release

# ── 3. Runtime ───────────────────────────────────────────────────────────────
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY --from=build /app/apps/backend/target/release/serious-shift-backend /usr/local/bin/app
COPY --from=web /web/out ./static
ENV PORT=8080 STATIC_DIR=/srv/static
EXPOSE 8080
CMD ["app"]
