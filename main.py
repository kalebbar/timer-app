import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Work timer with scheduled note breaks.")
    parser.add_argument(
        "--tui", action="store_true",
        help="use the keyboard-driven terminal interface instead of the desktop window",
    )
    args = parser.parse_args(argv)
    if args.tui:
        from tui import main as launch
    else:
        try:
            from gui import main as launch
        except ModuleNotFoundError as error:
            if error.name not in ("tkinter", "_tkinter"):
                raise
            parser.exit(1, "Tkinter is unavailable. Install Tk or use --tui.\n")
    try:
        launch()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
