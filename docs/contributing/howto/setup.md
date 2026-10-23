# Setup

From the repo root.

## Dev shell (nix)

```sh
nix develop          # python311 + openssl + pre-commit hooks installed
```

Without nix: ensure `python3` (3.11+) and `openssl` are on `PATH`.

## Run

```sh
./quine_packer.py bootstrap pack ./src -o dist/app   # src/ must hold main.py
./dist/app hello                                     # routes to main(['hello'])
./dist/app bootstrap unpack -C out                   # inverse of pack
```

## Checks

```sh
nix flake check                       # sandboxed hooks (ruff, nixfmt)
nix develop -c pre-commit run --all-files
```

## Round-trip smoke test

```sh
mkdir -p /tmp/qp-src && cp main.py /tmp/qp-src/
./quine_packer.py bootstrap pack /tmp/qp-src -o /tmp/qp-app
./quine_packer.py bootstrap pack /tmp/qp-src -o /tmp/qp-app2
cmp /tmp/qp-app /tmp/qp-app2 && echo deterministic
/tmp/qp-app bootstrap unpack -C /tmp/qp-out && diff -r /tmp/qp-src /tmp/qp-out
```
