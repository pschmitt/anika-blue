{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.anika-blue;
in
{
  options.services.anika-blue = {
    enable = lib.mkEnableOption "Anika Blue";

    package = lib.mkPackageOption pkgs "anika-blue" { };

    bindHost = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
      description = "Address to listen on.";
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 5000;
      description = "Port to listen on.";
    };

    dataDir = lib.mkOption {
      type = lib.types.path;
      default = "/var/lib/anika-blue";
      description = "Directory that holds the SQLite database.";
    };

    debug = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Log at debug level.";
    };

    secretKeyFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = ''
        File with the secret that signs session cookies. Without it, sessions
        reset whenever the service restarts.
      '';
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Open the port in the firewall.";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.anika-blue = {
      description = "Anika Blue";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];

      environment = {
        BIND_HOST = cfg.bindHost;
        BIND_PORT = toString cfg.port;
        DATABASE = "${cfg.dataDir}/anika_blue.db";
        RUST_LOG = if cfg.debug then "debug" else "info";
      }
      // lib.optionalAttrs (cfg.secretKeyFile != null) {
        SECRET_KEY_FILE = "%d/secret-key";
      };

      serviceConfig = {
        ExecStart = lib.getExe cfg.package;
        Restart = "always";
        RestartSec = 5;
        DynamicUser = true;
        StateDirectory = "anika-blue";
        ReadWritePaths = [ cfg.dataDir ];
        LoadCredential = lib.optional (cfg.secretKeyFile != null) "secret-key:${cfg.secretKeyFile}";

        CapabilityBoundingSet = "";
        LockPersonality = true;
        MemoryDenyWriteExecute = true;
        NoNewPrivileges = true;
        PrivateDevices = true;
        PrivateTmp = true;
        ProtectClock = true;
        ProtectControlGroups = true;
        ProtectHome = true;
        ProtectHostname = true;
        ProtectKernelLogs = true;
        ProtectKernelModules = true;
        ProtectKernelTunables = true;
        ProtectSystem = "strict";
        RestrictAddressFamilies = [
          "AF_INET"
          "AF_INET6"
        ];
        RestrictNamespaces = true;
        RestrictRealtime = true;
        SystemCallArchitectures = "native";
        SystemCallFilter = [ "@system-service" ];
      };
    };

    networking.firewall.allowedTCPPorts = lib.mkIf cfg.openFirewall [ cfg.port ];
  };
}
