from __future__ import annotations

import argparse
from pathlib import Path

from jah.app import TicketTui


def main() -> None:
    parser = argparse.ArgumentParser(description="Markdown ticket TUI")
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory containing flat markdown ticket files",
    )
    args = parser.parse_args()

    TicketTui(Path(args.directory).expanduser().resolve()).run()


if __name__ == "__main__":
    main()
