{
  lib,
  runCommand,
  # crane's library for this nixpkgs (`crane.mkLib pkgs`).
  craneLib,
}:
let
  cargoToml = lib.importTOML ../Cargo.toml;
  inherit (cargoToml.package) version;
  # The package's own version, normalized out of everything the dependency build
  # sees, so a release bump keeps that derivation (and the caches holding it).
  normalized =
    file:
    builtins.toFile (baseNameOf file) (
      builtins.replaceStrings
        [ "name = \"anika-blue\"\nversion = \"${version}\"" ]
        [ "name = \"anika-blue\"\nversion = \"0.0.0\"" ]
        (builtins.readFile file)
    );
  depsLock = normalized ../Cargo.lock;
  depsToml = normalized ../Cargo.toml;
  common = {
    pname = "anika-blue";
    inherit version src;
    strictDeps = true;
    cargoVendorDir = craneLib.vendorCargoDeps { cargoLock = depsLock; };
    cargoExtraArgs = "--locked";
  };
  depsSrc = runCommand "anika-blue-deps-src" { } ''
    mkdir -p $out/src
    cp ${depsToml} $out/Cargo.toml
    cp ${depsLock} $out/Cargo.lock
    echo 'fn main() {}' > $out/src/main.rs
    touch $out/src/lib.rs
  '';
  # The dependencies, built once: source changes and version bumps reuse them.
  deps = craneLib.buildDepsOnly (
    builtins.removeAttrs common [ "src" ]
    // {
      pname = "anika-blue-deps";
      version = "0";
      dummySrc = depsSrc;
    }
  );
  src = lib.fileset.toSource {
    root = ./..;
    fileset = lib.fileset.unions [
      ../Cargo.toml
      ../Cargo.lock
      ../src
      ../static
      ../templates
      ../tests
    ];
  };
in
craneLib.buildPackage (
  common
  // {
    cargoArtifacts = deps;
    doCheck = true;

    meta = {
      description = "Find your perfect shade of blue, one swatch at a time";
      homepage = "https://github.com/pschmitt/anika-blue";
      license = lib.licenses.gpl3Only;
      mainProgram = "anika-blue";
      platforms = lib.platforms.unix;
    };
  }
)
