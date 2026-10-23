#!/usr/bin/env python3
# Example user entry point. Replace with your own; keep `main(argv)`.


def main(argv: list[str]) -> int:
	print(f'hello from the packed payload, args={argv}')
	return 0


if __name__ == '__main__':
	import sys

	sys.exit(main(sys.argv[1:]))
