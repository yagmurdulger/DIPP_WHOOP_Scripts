#!/usr/bin/env python
import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Say hello from a simple script.")
    parser.add_argument("--name", default="World", help="Name to greet")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(f"Hello, {args.name}!")


if __name__ == "__main__":
    main()
