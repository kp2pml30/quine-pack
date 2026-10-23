{
  description = "quine-packer: a self-extracting, user-patchable single-file Python packer";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    systems.url = "github:nix-systems/default";

    git-hooks = {
      url = "github:cachix/git-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{ self, nixpkgs, ... }:
    let
      lib = nixpkgs.lib;
      forEachSystem = lib.genAttrs (import inputs.systems);
    in
    {
      packages = forEachSystem (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          # `result` is ONE self-extracting file: the /bin/sh + Python 3.11
          # runner stub with the app (src/ if present, else main.py) packed as
          # an appended, lzma+openssl blob. It still needs python3 and openssl
          # at the user's runtime.
          default = pkgs.stdenvNoCC.mkDerivation {
            pname = "quine-packer-dist";
            version = "0.1.0";
            src = ./.;
            # Keep the portable `#!/bin/sh`; nix would rewrite it to a store path.
            dontPatchShebangs = true;
            dontConfigure = true;
            nativeBuildInputs = [
              pkgs.python311
              pkgs.openssl
            ];
            buildPhase = ''
              if [ -d src ]; then pay=src; else mkdir payload && cp main.py payload/ && pay=payload; fi
              python3 quine_packer.py bootstrap pack "$pay" -o packed
            '';
            installPhase = ''
              install -Dm755 packed $out
            '';
          };

          # The packer CLI itself, wrapped with its runtime deps on PATH.
          packer = pkgs.stdenvNoCC.mkDerivation {
            pname = "quine-packer";
            version = "0.1.0";
            src = ./.;
            dontPatchShebangs = true;
            nativeBuildInputs = [ pkgs.makeWrapper ];
            installPhase = ''
              mkdir -p $out/bin $out/libexec
              cp quine_packer.py $out/libexec/quine-packer
              chmod +x $out/libexec/quine-packer
              makeWrapper $out/libexec/quine-packer $out/bin/quine-packer \
                --prefix PATH : ${
                  lib.makeBinPath [
                    pkgs.python311
                    pkgs.openssl
                  ]
                }
            '';
          };
        }
      );

      formatter = forEachSystem (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          config = self.checks.${system}.pre-commit-check.config;
          inherit (config) package configFile;
        in
        pkgs.writeShellScriptBin "pre-commit-run" ''
          ${pkgs.lib.getExe package} run --all-files --config ${configFile}
        ''
      );

      checks = forEachSystem (system: {
        pre-commit-check = inputs.git-hooks.lib.${system}.run {
          src = ./.;
          hooks =
            let
              pkgs = import nixpkgs { inherit system; };
            in
            {
              check-commit-message = {
                enable = true;
                name = "check commit message";
                description = "Validate the commit message against conventional-commit rules.";
                entry = "${pkgs.python311}/bin/python3 ${./support/scripts/check-commit-message.py} --message-file";
                language = "system";
                stages = [ "commit-msg" ];
              };

              nixfmt.enable = true;
              ruff.enable = true;
              ruff-format.enable = true;
            };
        };
      });

      devShells = forEachSystem (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          inherit (self.checks.${system}.pre-commit-check) shellHook enabledPackages;
        in
        {
          default = pkgs.mkShell {
            inherit shellHook;
            buildInputs = enabledPackages ++ [
              pkgs.python311
              pkgs.openssl
            ];
          };
        }
      );
    };
}
