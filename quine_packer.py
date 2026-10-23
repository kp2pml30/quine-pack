#!/bin/sh
# fmt: off
''':'
# ---------------------------------------------------------------------------
# POSIX sh preamble. Valid as a Python string literal (module docstring), so
# the same file is both a shell script and a Python module.
#
# A self-extracting file carries a raw binary blob appended after the marker.
# Python compiles a whole source file before running it and would choke on
# that binary, so we never run the file as a script: the `-c` bootstrap reads
# its own source, cuts it at the marker and execs only the head. Deps are just
# /bin/sh, python3 and openssl -- no sed/coreutils.
# ---------------------------------------------------------------------------
export QUINE_PACKER_NAME='quine-packer'
export QUINE_PACKER_PROG="$0"
command -v python3 >/dev/null 2>&1 || { echo "$NAME: python3 not found" >&2; exit 127; }
command -v openssl >/dev/null 2>&1 || { echo "$NAME: openssl not found" >&2; exit 127; }
exec python3 -B -c 'import sys; f=sys.argv[1]; sys.argv=[f]+sys.argv[2:]; s=open(f,"rb").read().split(b"\n#@QP-BLOB@\n",1)[0]; exec(compile(s,f,"exec"))' "$0" "$@"
'''
# fmt: on

import argparse
import importlib
import io
import lzma
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# --- swap these to rebrand -------------------------------------------------
NAME = os.getenv('QUINE_PACKER_NAME', 'quine-packer')
USER_MAIN_MODULE = 'main'
USER_MAIN_FUNC = 'main'

# DRM-like fake, intentionally public here: AES-256-CBC key as hex, 32 bytes.
KEY = 'deadbabe0a70deadcafe0ea750deadbeef0ded0ded0ded0ded0ded0ded0fffff'
# IV defaults to the first 16 bytes (32 hex chars) of KEY; override per run.
DEFAULT_IV = KEY[:32]

MARKER = b'#@QP-BLOB@\n'


def _self_and_args() -> tuple[Path, list[str]]:
	# The sh preamble and a direct dev run both put the real path at argv[0].
	return Path(sys.argv[0]), sys.argv[1:]


def split_self(path: Path) -> tuple[bytes, bytes]:
	# Returns (runner_text, blob). runner_text ends with a newline; blob is
	# empty for a bare runner stub.
	data = path.read_bytes()
	sep = b'\n' + MARKER
	pos = data.find(sep)
	if pos < 0:
		return data, b''
	return data[: pos + 1], data[pos + 1 + len(MARKER) :]


# --- deterministic zip (stored; outer lzma does the compression) -----------
def _entries(root: Path) -> list[Path]:
	out = []
	for p in root.rglob('*'):
		if p.is_dir() or p.suffix == '.pyc' or '__pycache__' in p.parts:
			continue
		out.append(p)
	out.sort(key=lambda p: p.relative_to(root).as_posix())
	return out


def build_zip(root: Path) -> bytes:
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_STORED) as z:
		for path in _entries(root):
			info = zipfile.ZipInfo(path.relative_to(root).as_posix())
			info.date_time = (1980, 1, 1, 0, 0, 0)
			info.create_system = 3
			info.external_attr = 0o644 << 16
			info.compress_type = zipfile.ZIP_STORED
			z.writestr(info, path.read_bytes())
	return buf.getvalue()


# --- openssl symmetric crypto ----------------------------------------------
def _openssl(data: bytes, iv: str, decrypt: bool) -> bytes:
	cmd = ['openssl', 'enc', '-aes-256-cbc', '-K', KEY, '-iv', iv]
	if decrypt:
		cmd.append('-d')
	r = subprocess.run(cmd, input=data, capture_output=True, check=False)
	if r.returncode != 0:
		raise SystemExit(
			f'{NAME}: openssl failed: {r.stderr.decode(errors="replace").strip()}'
		)
	return r.stdout


# The blob is `iv (16 bytes) || ciphertext` so it self-extracts with any IV.
def seal(payload: bytes, iv: str) -> bytes:
	body = _openssl(
		lzma.compress(payload, preset=9 | lzma.PRESET_EXTREME), iv, decrypt=False
	)
	return bytes.fromhex(iv) + body


def unseal(blob: bytes, iv: str | None = None) -> bytes:
	iv = iv or blob[:16].hex()
	try:
		return lzma.decompress(_openssl(blob[16:], iv, decrypt=True))
	except lzma.LZMAError:
		raise SystemExit(f'{NAME}: cannot decode blob (wrong key/iv or corrupt)')


# --- payload execution -----------------------------------------------------
def _run_user_main(src_dir: Path, args: list[str]) -> int:
	sys.path.insert(0, str(src_dir))
	mod = importlib.import_module(USER_MAIN_MODULE)
	fn = getattr(mod, USER_MAIN_FUNC)
	return int(fn(args) or 0)


def run_payload(self_path: Path, args: list[str]) -> int:
	# Packed: unpack blob to a temp dir and hand over to the user main.
	# Dev (no blob): import the user main from the file's own directory.
	_, blob = split_self(self_path)
	if not blob:
		return _run_user_main(self_path.resolve().parent, args)
	with tempfile.TemporaryDirectory(prefix=f'{NAME}-') as tmp:
		tmp_path = Path(tmp)
		zipfile.ZipFile(io.BytesIO(unseal(blob))).extractall(tmp_path)
		return _run_user_main(tmp_path, args)


# --- bootstrap subcommands -------------------------------------------------
def bootstrap(self_path: Path, args: list[str]) -> int:
	p = argparse.ArgumentParser(prog=f'{NAME} bootstrap')
	sub = p.add_subparsers(dest='cmd', required=True)

	sp = sub.add_parser('pack', help='build a self-extracting file from a directory')
	sp.add_argument('src', type=Path)
	sp.add_argument('-o', '--out', type=Path, required=True)
	sp.add_argument('--iv', default=DEFAULT_IV)

	su = sub.add_parser('unpack', help="extract this file's blob to a directory")
	su.add_argument('-C', '--dir', type=Path, default=Path('.'))
	su.add_argument('--iv', default=None, help='override the IV stored in the blob')

	sub.add_parser('blob', help='dump the appended blob to stdout')
	sub.add_parser('runner', help='dump the bare runner stub (no blob) to stdout')

	ns = p.parse_args(args)

	if ns.cmd == 'pack':
		runner_text, _ = split_self(self_path)
		if not runner_text.endswith(b'\n'):
			runner_text += b'\n'
		blob = seal(build_zip(ns.src), ns.iv)
		ns.out.write_bytes(runner_text + MARKER + blob)
		ns.out.chmod(0o755)
		return 0

	if ns.cmd == 'unpack':
		_, blob = split_self(self_path)
		if not blob:
			raise SystemExit(f'{NAME}: no blob in {self_path}')
		ns.dir.mkdir(parents=True, exist_ok=True)
		zipfile.ZipFile(io.BytesIO(unseal(blob, ns.iv))).extractall(ns.dir)
		return 0

	if ns.cmd == 'blob':
		_, blob = split_self(self_path)
		sys.stdout.buffer.write(blob)
		return 0

	if ns.cmd == 'runner':
		runner_text, _ = split_self(self_path)
		sys.stdout.buffer.write(runner_text)
		return 0

	return 2


def main() -> int:
	self_path, args = _self_and_args()
	if args and args[0] == 'bootstrap':
		return bootstrap(self_path, args[1:])
	return run_payload(self_path, args)


if __name__ == '__main__':
	sys.exit(main())
