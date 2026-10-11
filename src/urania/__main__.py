"""Entry point: python -m urania, the 'urania' command, and the frozen app."""
import sys


def main():
    from urania.cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
