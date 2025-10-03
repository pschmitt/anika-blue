# Anika Blue 💙

An interactive web application to help you discover your perfect shade of blue! Inspired by Tinder's swipe interface, users can classify different shades of blue as "Anika Blue" or "Not Anika Blue".

## Features

- **Interactive Tinder-like UI**: Swipe through different shades of blue
- **Personal Average**: Track your own "Anika Blue" based on your choices
- **Global Average**: See what the community collectively defines as "Anika Blue"
- **Hex Codes**: All shades display their hex color codes
- **Session Tracking**: Each user has their own persistent session
- **Dynamic Updates**: Smooth, interactive experience without page reloads

## Getting Started

### Prerequisites

- Python 3.7 or higher
- pip

Or use one of the alternative deployment methods below (Docker or Nix).

### Installation

1. Clone the repository:
```bash
git clone https://github.com/pschmitt/anika-blue.git
cd anika-blue
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

4. Open your browser and navigate to:
```
http://localhost:5000
```

### Docker

Run with Docker:

```bash
# Using Docker Hub image (once published)
docker run -p 5000:5000 -v anika-blue-data:/data ghcr.io/pschmitt/anika-blue:latest

# Or build locally
docker build -t anika-blue .
docker run -p 5000:5000 -v anika-blue-data:/data anika-blue
```

With docker-compose:

```yaml
version: '3.8'
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

### Nix/NixOS

With Nix flakes enabled:

```bash
# Run directly
nix run github:pschmitt/anika-blue

# Enter development shell
nix develop

# Build the package
nix build

# Build Docker image with Nix
nix build .#docker
docker load < result
```

For NixOS users, add to your configuration:

```nix
{
  services.anika-blue = {
    enable = true;
    port = 5000;
    dataDir = "/var/lib/anika-blue";
  };
}
```

## How It Works

1. **View a Shade**: A random blue shade is presented to you
2. **Make Your Choice**: 
   - Click "✓ Anika Blue" if you think it's Anika Blue
   - Click "❌ Not Anika Blue" if you don't think it's Anika Blue
   - Click "⏭️ Skip" to skip the shade
3. **Track Your Average**: Your personal Anika Blue average updates based on your "yes" choices
4. **See the Global Average**: View what everyone collectively defines as Anika Blue

## Technical Details

- **Backend**: Flask (Python)
- **Frontend**: HTML, CSS, JavaScript
- **Database**: SQLite
- **Session Management**: Flask sessions with secure tokens

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.
