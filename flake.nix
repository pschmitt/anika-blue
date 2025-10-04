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
                  FLASK_APP = "${pkg}/share/anika-blue/app.py";
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
          pythonEnv = pkgs.python312.withPackages (ps: with ps; [
            flask
            pillow
          ]);

          anika-blue = pkgs.stdenv.mkDerivation {
            pname = "anika-blue";
            version = "0.1.0";
            src = ./.;

            buildInputs = [ pythonEnv ];

            installPhase = ''
              mkdir -p $out/bin
              mkdir -p $out/share/anika-blue

              cp app.py $out/share/anika-blue/
              cp -r templates $out/share/anika-blue/

              cat > $out/bin/anika-blue <<EOF
              #!/usr/bin/env bash
              export DATABASE="\''${DATABASE:-\$HOME/.local/share/anika-blue/anika_blue.db}"
              mkdir -p "\$(dirname "\$DATABASE")"
              export FLASK_APP="$out/share/anika-blue/app.py"
              cd "$out/share/anika-blue"
              exec "${pythonEnv}/bin/python" app.py "\$@"
              EOF

              chmod +x $out/bin/anika-blue
            '';

            meta = with pkgs.lib; {
              description = "Interactive web application to discover your perfect shade of blue";
              homepage = "https://github.com/pschmitt/anika-blue";
              license = licenses.gpl3Only;
              maintainers = [ ];
              platforms = platforms.all;
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
              Cmd = [
                "${pythonEnv}/bin/python"
                "/app/app.py"
              ];
              WorkingDir = "/app";
              ExposedPorts."5000/tcp" = { };
              Env = [
                "FLASK_APP=/app/app.py"
                "DATABASE=/data/anika_blue.db"
                "PYTHONUNBUFFERED=1"
              ];
            };

            extraCommands = ''
              mkdir -p app data
              cp ${./app.py} app/app.py
              cp -r ${./templates} app/templates
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
              python312Packages.pip
              python312Packages.setuptools
              sqlite
              python312Packages.black
              python312Packages.flake8
              python312Packages.pytest
            ];

            shellHook = ''
              echo "🔵 Anika Blue Development Environment"
              echo "======================================"
              echo "Python: $(python --version)"
              echo "Flask: $(python -c 'import flask; print(flask.__version__)')"
              echo
              echo "Run 'python app.py' to start the development server"
              echo "Run 'nix build .#docker' to build Docker image"
              echo
              export DATABASE="''${DATABASE:-$PWD/anika_blue.db}"
              export FLASK_APP="$PWD/app.py"
            '';
          };
        };
    };
}
