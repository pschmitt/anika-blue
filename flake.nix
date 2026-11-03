{
  description = "Anika Blue - find your perfect shade of blue";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    # Builds the dependencies in their own derivation, so CI caches and hosts
    # reuse them instead of recompiling every crate on each change.
    crane.url = "github:ipetkov/crane";
  };

  outputs =
    {
      self,
      nixpkgs,
      crane,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      # x86_64-linux package builds and checks run on the self-hosted nixbot.
      # aarch64-linux builds natively on GitHub's arm runners (the nix-aarch64
      # job of .github/workflows/ci.yaml).
      hydraJobs = nixpkgs.lib.genAttrs [ "x86_64-linux" ] (system: {
        packages = self.packages.${system} or { };
        # Builders have no /dev/kvm; the VM test stays on GitHub Actions.
        checks = builtins.removeAttrs (self.checks.${system} or { }) [ "nixos" ];
      });

      packages = forAllSystems (
        pkgs:
        let
          anika-blue = pkgs.callPackage ./nix/package.nix { craneLib = crane.mkLib pkgs; };
        in
        {
          inherit anika-blue;
          default = anika-blue;
        }
        // nixpkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux rec {
          # Fully static (musl) binary, used for the container image.
          anika-blue-static = pkgs.pkgsStatic.callPackage ./nix/package.nix {
            craneLib = crane.mkLib pkgs.pkgsStatic;
          };
          image = pkgs.dockerTools.buildLayeredImage {
            name = "ghcr.io/pschmitt/anika-blue";
            tag = anika-blue-static.version;
            extraCommands = "mkdir -p data";
            config = {
              Entrypoint = [ "${anika-blue-static}/bin/anika-blue" ];
              Env = [
                "BIND_HOST=0.0.0.0"
                "BIND_PORT=5000"
                "DATABASE=/data/anika_blue.db"
              ];
              ExposedPorts."5000/tcp" = { };
              Volumes."/data" = { };
            };
          };
        }
      );

      overlays.default = final: _prev: {
        anika-blue = final.callPackage ./nix/package.nix { craneLib = crane.mkLib final; };
      };

      nixosModules.default = {
        imports = [ ./nix/module.nix ];
        nixpkgs.overlays = [ self.overlays.default ];
      };

      checks = forAllSystems (
        pkgs:
        {
          inherit (self.packages.${pkgs.stdenv.hostPlatform.system}) anika-blue;
        }
        // nixpkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
          nixos = pkgs.testers.runNixOSTest (import ./nix/test.nix { inherit self; });
        }
      );

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            cargo
            clippy
            rust-analyzer
            rustc
            rustfmt
            nixfmt
            statix
            deadnix
          ];
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt-tree);
    };
}
