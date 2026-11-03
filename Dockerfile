# syntax=docker/dockerfile:1

# Static musl build; the cache mounts keep crates and build artifacts between
# CI runs (BuildKit cache in the GitHub Actions cache).
FROM rust:1-alpine AS build
RUN apk add --no-cache musl-dev
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY src ./src
COPY static ./static
COPY templates ./templates
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/src/target \
    cargo build --release --locked \
    && install -Dm755 target/release/anika-blue /out/anika-blue \
    && mkdir -p /out/data

FROM scratch
COPY --from=build /out /
ENV BIND_HOST=0.0.0.0 \
    BIND_PORT=5000 \
    DATABASE=/data/anika_blue.db
VOLUME /data
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["/anika-blue", "healthcheck"]
ENTRYPOINT ["/anika-blue"]
