import argparse

from .report.replay_report import run_ingest


def main() -> None:
    parser = argparse.ArgumentParser(prog="rotatool")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="parse raw rota workbooks")
    ingest.add_argument("--raw", default="data/raw")
    ingest.add_argument("--out", default="data/processed")
    ingest.add_argument(
        "--staff", default="data/raw/Staff master guide for rota.xlsx"
    )

    args = parser.parse_args()
    if args.command == "ingest":
        path = run_ingest(args.raw, args.out, args.staff)
        print(f"report written to {path}")


if __name__ == "__main__":
    main()
