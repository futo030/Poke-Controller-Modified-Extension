import argparse
from pathlib import Path

from pokecontrollerext import run_app


if __name__ == '__main__':
    # args
    parser = argparse.ArgumentParser(description="Switch/GC automation support software using Python")
    parser.add_argument("--profile", "-p", help="profile", type=str, default="default")
    args = parser.parse_args()

    base_dir = Path(__file__).parent

    run_app(base_dir=base_dir, profile=args.profile)
