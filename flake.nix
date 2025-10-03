{
  description = "Anika Blue - Interactive blue shade classifier";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        
        pythonEnv = pkgs.python312.withPackages (ps: with ps; [
          flask
        ]);

        anika-blue = pkgs.stdenv.mkDerivation {
          pname = "anika-blue";
          version = "0.1.0";

          src = ./.;

          buildInputs = [ pythonEnv ];

          installPhase = ''
            mkdir -p $out/{bin,share/anika-blue}
            
            # Copy application files
            cp app.py $out/share/anika-blue/
            cp -r templates $out/share/anika-blue/
            
            # Create wrapper script
            cat > $out/bin/anika-blue <<EOF
            #!${pkgs.bash}/bin/bash
            export FLASK_APP=$out/share/anika-blue/app.py
            export DATABASE=\''${DATABASE:-\$HOME/.local/share/anika-blue/anika_blue.db}
            mkdir -p \$(dirname \$DATABASE)
            cd $out/share/anika-blue
            exec ${pythonEnv}/bin/python app.py "\$@"
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
            Cmd = [ "${pythonEnv}/bin/python" "/app/app.py" ];
            WorkingDir = "/app";
            ExposedPorts = {
              "5000/tcp" = {};
            };
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

        apps = {
          default = {
            type = "app";
            program = "${anika-blue}/bin/anika-blue";
          };
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            pythonEnv
            python312Packages.pip
            python312Packages.setuptools
            sqlite
            # Development tools
            python312Packages.black
            python312Packages.flake8
            python312Packages.pytest
          ];

          shellHook = ''
            echo "🔵 Anika Blue Development Environment"
            echo "======================================"
            echo "Python: $(python --version)"
            echo "Flask: $(python -c 'import flask; print(flask.__version__)')"
            echo ""
            echo "Run 'python app.py' to start the development server"
            echo "Run 'nix build .#docker' to build Docker image"
            echo ""
            
            # Set up local database directory
            export DATABASE="''${DATABASE:-$PWD/anika_blue.db}"
            export FLASK_APP="$PWD/app.py"
          '';
        };

        # NixOS module for system-wide deployment
        nixosModules.default = { config, lib, pkgs, ... }:
          with lib;
          let
            cfg = config.services.anika-blue;
          in
          {
            options.services.anika-blue = {
              enable = mkEnableOption "Anika Blue service";

              port = mkOption {
                type = types.port;
                default = 5000;
                description = "Port to run the service on";
              };

              dataDir = mkOption {
                type = types.path;
                default = "/var/lib/anika-blue";
                description = "Directory to store the database";
              };

              secretKeyFile = mkOption {
                type = types.nullOr types.path;
                default = null;
                description = "Path to file containing the secret key";
              };
            };

            config = mkIf cfg.enable {
              systemd.services.anika-blue = {
                description = "Anika Blue - Interactive blue shade classifier";
                wantedBy = [ "multi-user.target" ];
                after = [ "network.target" ];

                environment = {
                  DATABASE = "${cfg.dataDir}/anika_blue.db";
                  FLASK_APP = "${anika-blue}/share/anika-blue/app.py";
                } // optionalAttrs (cfg.secretKeyFile != null) {
                  SECRET_KEY_FILE = cfg.secretKeyFile;
                };

                serviceConfig = {
                  Type = "simple";
                  ExecStart = "${anika-blue}/bin/anika-blue";
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
            };
          };
      }
    );
}
