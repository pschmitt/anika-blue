# Deployment

Anika Blue is a single binary that serves HTTP and keeps its data in one
SQLite file.

## Configuration

Every option is a flag and an environment variable (`anika-blue --help`):

| Variable | Flag | Default | |
|---|---|---|---|
| `BIND_HOST` | `--host` | `0.0.0.0` | Address to listen on |
| `BIND_PORT` | `--port` | `5000` | Port to listen on |
| `DATABASE` | `--database` | `anika_blue.db` | SQLite database file |
| `SECRET_KEY` | `--secret-key` | random | Secret that signs session cookies |
| `SECRET_KEY_FILE` | `--secret-key-file` | | File with the secret; wins over `SECRET_KEY` |
| `RUST_LOG` | | `info` | Log filter |

Without a secret, a random one is generated at start, so every restart ends
all sessions. Visitors can still restore theirs with their Anika Blue.

`/healthz` answers `ok`; `anika-blue healthcheck` checks it from inside the
container.

## Docker

Images for `linux/amd64` and `linux/arm64` are published to
`ghcr.io/pschmitt/anika-blue`: `latest` follows `main`, version tags follow
releases. The image holds only the static binary; data lives in `/data`.

```sh
docker run -d -p 5000:5000 -v anika-blue:/data -e SECRET_KEY=change-me \
  ghcr.io/pschmitt/anika-blue
```

With Docker Compose, set `SECRET_KEY` in the environment or an `.env` file and
run `docker compose up -d` with the repository's
[docker-compose.yml](../docker-compose.yml).

The flake builds the same image without Docker:

```sh
nix build .#image
docker load < result
```

## NixOS

```nix
{
  inputs.anika-blue.url = "github:pschmitt/anika-blue";

  outputs = { nixpkgs, anika-blue, ... }: {
    nixosConfigurations.example = nixpkgs.lib.nixosSystem {
      modules = [
        anika-blue.nixosModules.default
        {
          services.anika-blue = {
            enable = true;
            port = 5000;                          # default
            bindHost = "127.0.0.1";               # default; put a proxy in front
            secretKeyFile = "/run/secrets/anika-blue";
            dataDir = "/var/lib/anika-blue";      # default
            debug = false;                        # default; RUST_LOG=debug
            openFirewall = false;                 # default
          };
        }
      ];
    };
  };
}
```

The service runs as a dynamic user with a hardened systemd sandbox and keeps
its database in `dataDir`. The secret file is passed as a systemd
credential, so it can stay readable by root only.

## Upgrading from the Python version

The database schema is unchanged; point `DATABASE` at the old file. Session
cookies of the Python version are not valid any more: visitors get a new
session and can restore their old one with their Anika Blue.
