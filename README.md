# quine-packer

A self-extracting, user-patchable single-file Python packer — ship one `/bin/sh` script with a compressed, encrypted payload appended to its tail.

[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![vibe coded](https://img.shields.io/badge/vibe-coded-purple.svg)](docs/README.md)

## Background

Software in the 80s shipped as one self-extracting file you could read, run and patch yourself. `quine-packer` is that: a `/bin/sh` + Python 3.11 polyglot runner with a `lzma -9` compressed, `openssl` AES-256-CBC encrypted blob appended at the end. Users extract and run it themselves; the encryption key is inline and public on purpose (it is DRM-like, not security).

## Install

Requires Python 3.11 and `openssl` on `PATH` at runtime — the script prints an error and exits non-zero if either is missing.

```sh
# nix build → `result` is ONE self-extracting file (stub + packed app)
nix build
./result                      # runs the packed app (needs python3 + openssl)

# the packer CLI itself
nix run .#packer -- --help
nix build .#packer && ./result/bin/quine-packer --help

# or just copy the one file
cp quine_packer.py ~/.local/bin/quine-packer && chmod +x ~/.local/bin/quine-packer
```

Rename: everything swaps from the `NAME` constants in `quine_packer.py` (one in the sh preamble, one in Python) plus the file name.

## Usage

The runner has two roles: `bootstrap` manages the package itself; everything else is routed to your `main(argv)`.

```sh
# build a self-extracting file from a source directory (must contain main.py)
./quine_packer.py bootstrap pack ./src -o dist/app
./dist/app arg1 arg2            # runs src/main.py:main(['arg1', 'arg2'])

# bootstrap subcommands
./dist/app bootstrap unpack -C out   # extract the blob (inverse of pack)
./dist/app bootstrap blob > blob.bin # dump the appended blob
./dist/app bootstrap runner > bare   # dump the runner stub, no blob
```

Layout of a packed file:

```
#!/bin/sh … Python runner stub …
#@QP-BLOB@
<lzma -9 | openssl aes-256-cbc : zip of the source>
```

### Encryption

- Key: inline hex (`KEY` in `quine_packer.py`), AES-256-CBC, public by design
- IV: `--iv HEX` on `pack` (default = first 16 bytes of the key) is stored as a 16-byte blob header, so a packed file self-extracts with any IV; `unpack --iv` only overrides it for recovery
- Compression: `lzma` preset `9 | EXTREME`; the inner zip is `STORED` and built deterministically, so packing is byte-for-byte reproducible within a fixed `liblzma`. Note the zip forces mode `0644` and skips directories — exec bits, empty dirs and symlinks are not preserved

### Writing your main

Copy your code into the source directory with a `main.py` exposing `def main(argv: list[str]) -> int`. See [`main.py`](main.py). In dev (no blob) the runner imports `main` from its own directory; when packed it imports from the unpacked blob.

## Contributing

See [docs/contributing/README.md](docs/contributing/README.md).

## License

GPL-3.0 © 2026 kp2pml30
