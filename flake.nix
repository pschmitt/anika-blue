{
  description = "Anika Blue - Interactive blue shade classifier";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs =
    inputs@{
      self,
      flake-parts,
      nixpkgs,
      ...
    }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      flake = {
        # System-agnostic NixOS module, available as `nixosModules.default`
        nixosModules.default =
          {
            config,
            lib,
            pkgs,
            ...
          }:
          let
            cfg = config.services.anika-blue;
            pkg = self.packages.${config.nixpkgs.hostPlatform.system}.anika-blue;
          in
          {
            options.services.anika-blue = {
              enable = lib.mkEnableOption "Anika Blue service";

              debug = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable debug mode";
              };

              bindHost = lib.mkOption {
                type = lib.types.str;
                default = "0.0.0.0";
                description = "Host to bind the service to";
              };

              port = lib.mkOption {
                type = lib.types.port;
                default = 5000;
                description = "Port to run the service on";
              };

              dataDir = lib.mkOption {
                type = lib.types.path;
                default = "/var/lib/anika-blue";
                description = "Directory to store the database";
              };

              secretKeyFile = lib.mkOption {
                type = lib.types.nullOr lib.types.path;
                default = null;
                description = "Path to file containing the secret key";
              };
            };

            config = lib.mkIf cfg.enable {
              systemd.services.anika-blue = {
                description = "Anika Blue - Interactive blue shade classifier";
                wantedBy = [ "multi-user.target" ];
                after = [ "network.target" ];

                environment = {
                  DEBUG = if cfg.debug then "1" else "";
                  DATABASE = "${cfg.dataDir}/anika_blue.db";
                  BIND_HOST = "${cfg.bindHost}";
                  BIND_PORT = "${toString cfg.port}";
                }
                // lib.optionalAttrs (cfg.secretKeyFile != null) {
                  SECRET_KEY_FILE = cfg.secretKeyFile;
                };

                serviceConfig = {
                  Type = "simple";
                  ExecStart = "${pkg}/bin/anika-blue";
                  Restart = "always";
                  RestartSec = 10;
                  StateDirectory = "anika-blue";
                  DynamicUser = true;

                  # Security hardening
                  NoNewPrivileges = true;
                  PrivateTmp = true;
                  ProtectSystem = "strict";
                  ProtectHome = true;
                  ReadWritePaths = cfg.dataDir;
                };
              };

              # Optionally, open the port if you like:
              # networking.firewall.allowedTCPPorts = [ cfg.port ];
            };
          };
      };

      perSystem =
        {
          self',
          pkgs,
          system,
          ...
        }:
        let
          pythonEnv = pkgs.python313.withPackages (
            ps: with ps; [
              flask
              pillow
            ]
          );

          cleanSrc = pkgs.lib.cleanSourceWith {
            src = ./.;
            filter = path: type:
              let
                base = builtins.baseNameOf path;
              in
              pkgs.lib.cleanSourceFilter path type
              && base != "__pycache__"
              && base != ".pytest_cache"
              && base != "result"
              && base != "dist";
          };

          anika-blue = pkgs.python3Packages.buildPythonPackage {
            pname = "anika-blue";
            version = "0.1.0";
            pyproject = true;
            src = ./.;

            nativeBuildInputs = [
              pkgs.python3Packages.uv-build
            ];

            propagatedBuildInputs = with pkgs.python3Packages; [
              flask
              pillow
            ];

            # Sanity check import at build time
            pythonImportsCheck = [ "anika_blue" ];

            meta = with pkgs.lib; {
              description = "Interactive web application to discover your perfect shade of blue";
              homepage = "https://github.com/pschmitt/anika-blue";
              license = licenses.gpl3Only;
              maintainers = [ ];
              platforms = platforms.all;
              mainProgram = "anika-blue";
            };
          };

          dockerImage = pkgs.dockerTools.buildLayeredImage {
            name = "anika-blue";
            tag = "latest";

            contents = [
              pythonEnv
              pkgs.bash
              pkgs.coreutils
              pkgs.sqlite
            ];

            config = {
              Cmd = [ "python" "-m" "anika_blue" ];
              WorkingDir = "/app";
              ExposedPorts."5000/tcp" = { };
              Env = [
                "DATABASE=/data/anika_blue.db"
                "BIND_HOST=0.0.0.0"
                "BIND_PORT=5000"
                "PYTHONUNBUFFERED=1"
                "PYTHONPATH=/app"
              ];
              Healthcheck = {
                Test = [
                  "CMD-SHELL"
                  "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:5000/').read()\" || exit 1"
                ];
                Interval = 30000000000; # 30s in nanoseconds
                Timeout = 3000000000; # 3s
                StartPeriod = 5000000000; # 5s
                Retries = 3;
              };
            };

            extraCommands = ''
              mkdir -p app data
              cp -R ${cleanSrc}/. app/
            '';
          };
        in
        {
          packages = {
            default = anika-blue;
            anika-blue = anika-blue;
            docker = dockerImage;
          };

          apps.default = {
            type = "app";
            program = "${self'.packages.anika-blue}/bin/anika-blue";
          };

          devShells.default = pkgs.mkShell {
            buildInputs = with pkgs; [
              pythonEnv
              python313Packages.black
              python313Packages.pip
              python313Packages.pytest
              python313Packages.setuptools
              ruff
              sqlite
            ];

            shellHook = ''
              echo "🔵 Anika Blue Development Environment"
              echo "======================================"
              echo "Python: $(python --version)"
              echo "Flask: $(python -c 'import importlib.metadata; print(importlib.metadata.version("flask"))')"
              echo
              echo "Commands:"
              echo "  python -m anika_blue          # Start development server"
              echo "  pytest tests/ -v              # Run tests"
              echo "  black .                       # Format code"
              echo "  ruff check anika_blue tests/  # Lint code"
              echo "  nix build '.#docker'          # Build Docker image"
              echo
              export DATABASE="''${DATABASE:-$PWD/anika_blue.db}"
            '';
          };
        };
    };
}
