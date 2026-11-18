"""Fetch the fixed OPSD snapshot and run the grid-load transfer benchmark."""
import argparse
import json
from pathlib import Path

from grid_data import fetch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "benchmark"):
        commands.add_parser(name).add_argument("--csv", required=True, type=Path)
    commands.choices["benchmark"].add_argument("--out", required=True, type=Path)
    commands.choices["benchmark"].add_argument("--threads", type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            fetch(args.csv)
        else:
            from benchmark import benchmark
            summary = benchmark(args.csv, args.out, args.threads)
            for area, models in summary["test"].items():
                print(area, json.dumps({name: round(values["mae_mw"], 2) for name, values in models.items()}))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
