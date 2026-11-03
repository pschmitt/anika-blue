# Development

The flake's dev shell has the Rust toolchain and the Nix linters:

```sh
nix develop                         # or direnv: .envrc runs `use flake`
cargo run                           # http://127.0.0.1:5000
cargo test                          # unit and HTTP tests
cargo fmt && cargo clippy --all-targets -- -D warnings
```

## Layout

| Path | |
|---|---|
| `src/lib.rs` | Router, handlers, sessions and the database |
| `src/color.rs` | Color parsing, names and contrast |
| `src/css3.rs` | The CSS named colors, generated from the webcolors table |
| `templates/` | MiniJinja templates; `index.html` includes the other two |
| `static/` | The CSS and JavaScript, embedded into the binary |
| `nix/` | The package, the NixOS module and its VM test |

Templates and static files are compiled in, so a change needs a rebuild. Their
URLs carry a hash of the content, which lets browsers cache them for a year.

## CI

- `lint`: rustfmt and clippy (shared `rust-lint` workflow of
  [ci-workflows](https://github.com/pschmitt/ci-workflows)) and a syntax check
  of `static/app.js`; `Nix lint` runs the shared `nix-lint` workflow (nixfmt,
  statix, deadnix).
- `test`: `cargo test`, the NixOS VM test, and the aarch64-linux Nix build on
  GitHub's arm runners.
- nixbot builds the x86_64-linux packages and checks (`hydraJobs`).
- `docker`: native amd64 and arm64 image builds, merged into one manifest.
- `update-flake-lock`: a weekly `flake.lock` update; Renovate handles crates,
  actions and the Docker base image.

## Screenshots

The README screenshots come from a throwaway server with made-up votes:

```sh
cargo build
nix shell nixpkgs#chromium nixpkgs#nodejs nixpkgs#curl -c tools/screenshots/run.sh
```
