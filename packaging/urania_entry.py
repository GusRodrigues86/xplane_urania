"""Entry point of the frozen app (PyInstaller). Same as 'python -m urania'."""
import sys

from urania.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
