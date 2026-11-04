{ self }:
{
  name = "anika-blue";

  nodes.machine =
    { pkgs, ... }:
    {
      # The module itself; nixosModules.default would also set an overlay,
      # which the test's read-only pkgs do not allow.
      imports = [ ./module.nix ];

      services.anika-blue = {
        enable = true;
        package = self.packages.${pkgs.stdenv.hostPlatform.system}.anika-blue;
        secretKeyFile = builtins.toFile "secret-key" "not-a-secret";
      };
    };

  testScript = ''
    machine.wait_for_unit("anika-blue.service")
    machine.wait_for_open_port(5000)
    machine.succeed("curl -sf http://127.0.0.1:5000/healthz")
    # Not `| grep -q`: it closes the pipe early and curl fails under pipefail.
    page = machine.succeed("curl -sf http://127.0.0.1:5000/")
    assert "Is this" in page, page
    machine.succeed("test -f /var/lib/anika-blue/anika_blue.db")
  '';
}
