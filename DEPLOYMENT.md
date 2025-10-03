# Deployment Guide

This guide covers various deployment options for Anika Blue.

## Table of Contents

- [Docker](#docker)
- [Nix/NixOS](#nixnixos)
- [Traditional Python](#traditional-python)

## Docker

### Quick Start

The easiest way to run Anika Blue with Docker:

```bash
docker run -p 5000:5000 -v anika-blue-data:/data ghcr.io/pschmitt/anika-blue:latest
```

Then visit http://localhost:5000

### Using Docker Compose

1. Create a `docker-compose.yml` file (or use the one in this repo):

```yaml
services:
  anika-blue:
    image: ghcr.io/pschmitt/anika-blue:latest
    ports:
      - "5000:5000"
    volumes:
      - anika-blue-data:/data
    environment:
      - SECRET_KEY=your-secret-key-here
    restart: unless-stopped

volumes:
  anika-blue-data:
```

2. Run:

```bash
docker-compose up -d
```

### Building Locally

```bash
docker build -t anika-blue .
docker run -p 5000:5000 -v anika-blue-data:/data anika-blue
```

### Environment Variables

- `DEBUG`: If set this will enable the flask debug mode (default: unset)
- `DATABASE`: Path to SQLite database file (default: `/data/anika_blue.db`)
- `SECRET_KEY`: Flask secret key for sessions (auto-generated if not set)
- `BIND_HOST`: Interface to listen on (default: `0.0.0.0`)
- `BIND_PORT`: Port to start the service on (default: `5000`)

### Persistent Data

Use a volume to persist the database:

```bash
docker volume create anika-blue-data
docker run -p 5000:5000 -v anika-blue-data:/data ghcr.io/pschmitt/anika-blue:latest
```

## Nix/NixOS

### Prerequisites

Ensure Nix is installed with flakes enabled:

```bash
# Add to ~/.config/nix/nix.conf or /etc/nix/nix.conf
experimental-features = nix-command flakes
```

### Quick Run

```bash
nix run github:pschmitt/anika-blue
```

### Development Shell

```bash
# Clone the repository
git clone https://github.com/pschmitt/anika-blue.git
cd anika-blue

# Enter development shell
nix develop

# Run the app
python app.py
```

### Building the Package

```bash
# Build the Nix package
nix build

# Run the built package
./result/bin/anika-blue
```

### Building Docker Image with Nix

```bash
# Build Docker image using Nix
nix build .#docker

# Load into Docker
docker load < result

# Run the image
docker run -p 5000:5000 anika-blue:latest
```

### NixOS Module

For NixOS users, add to your configuration:

```nix
{
  inputs.anika-blue.url = "github:pschmitt/anika-blue";

  outputs = { self, nixpkgs, anika-blue, ... }: {
    nixosConfigurations.yourhostname = nixpkgs.lib.nixosSystem {
      modules = [
        anika-blue.nixosModules.default
        {
          services.anika-blue = {
            enable = true;
            bindHost = "0.0.0.0";
            port = 5000;
            dataDir = "/var/lib/anika-blue";
            # Optional: path to file containing secret key
            # secretKeyFile = "/run/secrets/anika-blue-secret";
          };
        }
      ];
    };
  };
}
```

Then rebuild your system:

```bash
sudo nixos-rebuild switch
```

The service will be available at http://localhost:5000

### With direnv

If you have direnv installed:

```bash
# Clone and enter directory
git clone https://github.com/pschmitt/anika-blue.git
cd anika-blue

# Allow direnv
direnv allow

# Development environment is now active!
```

## Traditional Python

### Requirements

- Python 3.7 or higher
- pip

### Installation

1. Clone the repository:
```bash
git clone https://github.com/pschmitt/anika-blue.git
cd anika-blue
```

2. Create virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
python app.py
```

5. Visit http://localhost:5000

### Environment Variables

- `DATABASE`: Path to SQLite database file (default: `anika_blue.db`)
- `SECRET_KEY`: Flask secret key for sessions (auto-generated if not set)

### Production Deployment

For production, use a WSGI server like gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

Or with environment variables:

```bash
export DATABASE=/var/lib/anika-blue/anika_blue.db
export SECRET_KEY=your-secure-secret-key
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## GitHub Container Registry

The Docker images are automatically built and published to GitHub Container Registry (GHCR) on:

- Every push to `main` branch → tagged as `latest` and `main`
- Every tag push `v*` → tagged with version numbers
- Pull requests → built but not pushed

Images are available at: `ghcr.io/pschmitt/anika-blue`

### Available Tags

- `latest` - Latest stable version from main branch
- `main` - Latest commit on main branch
- `vX.Y.Z` - Specific version tags
- `X.Y` - Major.minor version
- `X` - Major version
- `<branch>-<sha>` - Specific commit SHA

### Multi-architecture Support

Images are built for:
- `linux/amd64` (Intel/AMD 64-bit)
- `linux/arm64` (ARM 64-bit, including Apple Silicon and Raspberry Pi)
