import sys

from mem20wasmz.core import cli

DEFAULT_PORT = 8766


def _inject_port(argv):
    argv = list(argv)
    if "serve" in argv:
        if "--port" not in argv:
            argv += ["--port", str(DEFAULT_PORT)]
    return argv


if __name__ == "__main__":
    sys.exit(cli(_inject_port(sys.argv[1:])))
