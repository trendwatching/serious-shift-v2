# Backend image — serves the read API *and* the exported SPA from one process,
# so there is no second always-on service and no cross-origin hop.
#
# BUILD CONTEXT IS THE REPO ROOT:  docker build -f apps/backend/Dockerfile .
# The runtime image carries apps/frontend's static export, so the frontend must
# be in the context. The crate no longer embeds any prompt text — /api/personalize
# was the only consumer and it had no callers.

# ── 1. Frontend: static export ───────────────────────────────────────────────
FROM node:22-slim@sha256:f32b81066cde10a75dbac96646099533316d94bac4150c55da1636e1f0ffdc46 AS web
WORKDIR /web
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci
COPY apps/frontend/ ./
RUN npm run build          # → /web/out

# ── 2. Backend: compile ──────────────────────────────────────────────────────
FROM rust:1-bookworm@sha256:77fac8b98f9f46062bb680b6d25d5bcaabfc400143952ebc572e924bcbedc3fa AS build
WORKDIR /app/apps/backend
# Dependencies first, against a stub main, so editing src/ doesn't recompile
# every crate in the tree — that is the bulk of the build time.
COPY apps/backend/Cargo.toml apps/backend/Cargo.lock ./
RUN mkdir src && echo 'fn main() {}' > src/main.rs \
    && cargo build --release \
    && rm -rf src
COPY apps/backend/src ./src
# Touch so cargo doesn't reuse the stub's fingerprint for the real main.rs.
RUN touch src/main.rs && cargo build --release

# ── 3. Runtime ───────────────────────────────────────────────────────────────
FROM debian:bookworm-slim@sha256:7b140f374b289a7c2befc338f42ebe6441b7ea838a042bbd5acbfca6ec875818
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && groupadd --system --gid 10001 serious \
    && useradd --system --uid 10001 --gid serious --no-create-home serious \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY --from=build /app/apps/backend/target/release/serious-shift-backend /usr/local/bin/app
COPY --from=web /web/out ./static
ENV PORT=8080 STATIC_DIR=/srv/static
EXPOSE 8080
USER 10001:10001
CMD ["app"]
