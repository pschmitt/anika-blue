# Agent Guidelines for Anika Blue

Anika Blue is a small web app for voting on shades of blue: a Rust (axum,
MiniJinja, rusqlite) server with server-rendered templates and a little vanilla
JavaScript. See [docs/development.md](docs/development.md) for the layout.

Before changing workflows, check for reusable workflows or actions in
[ci-workflows](https://github.com/pschmitt/ci-workflows) and preserve existing
triggers, inputs, permissions, and check coverage.

## Checks

Run these before finishing a change (in `nix develop`):

```sh
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
node --check static/app.js
nixfmt --check flake.nix nix/*.nix && statix check . && deadnix --fail nix flake.nix
```

Build on an ad-hoc `rworker` (see the `rworker` skill) or a remote build host, not on the machine the agent runs on.

## Conventions

- Keep the frontend dependency-free: no JavaScript framework, no web fonts, no
  build step. Templates and static files are embedded with `include_str!`.
- Keep the first page complete after one request (shade and stats rendered
  inline); the client prefetches the next shade so votes swap instantly.
- Color accuracy matters: the swatch shows the exact shade on a neutral
  background. Do not tint or filter it.
- The SQLite schema must stay compatible with existing databases.
- `src/css3.rs` is generated; regenerate it rather than editing names by hand.
- When the UI changes visibly, refresh the README screenshots with
  `tools/screenshots/run.sh` (made-up data only).
- Dependencies: Cargo for Rust; the flake (crane) builds from `Cargo.lock`, so
  no hashes need updating.
- Strip trailing whitespace; use LF line endings and spaces for indentation.
