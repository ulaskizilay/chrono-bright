"""Allow running the package directly with `python -m chronobright`."""

from __future__ import annotations

import argparse
import sys

from chronobright import __version__
from chronobright.logger import get_logger
from chronobright.single_instance import SingleInstanceLock
from chronobright.ui.app import ChronoBrightApp

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="chronobright", description="Scheduled display brightness control")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Start hidden in the system tray instead of showing the window.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--enable-autostart",
        action="store_true",
        help="Enable launch at Windows login and exit.",
    )
    group.add_argument(
        "--disable-autostart",
        action="store_true",
        help="Disable launch at Windows login and exit.",
    )
    return parser.parse_args(argv)


def _handle_autostart_flags(args: argparse.Namespace) -> bool:
    """Handle --enable/--disable-autostart. Returns True if the app should exit."""
    if not (args.enable_autostart or args.disable_autostart):
        return False
    from chronobright.services.autostart_service import AutostartService

    svc = AutostartService()
    try:
        svc.set_enabled(bool(args.enable_autostart))
        print(f"Autostart {'enabled' if args.enable_autostart else 'disabled'}.")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    return True


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if _handle_autostart_flags(args):
        return
    lock = SingleInstanceLock()
    if not lock.acquire():
        print("ChronoBright is already running.", file=sys.stderr)
        sys.exit(2)
        return

    app: ChronoBrightApp | None = None
    try:
        app = ChronoBrightApp()
        if args.minimized:
            app.withdraw()
            app._window_in_tray = True
            app._tray_service.set_window_visible(False)
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down.")
    except Exception:
        logger.exception("Fatal error in application")
        sys.exit(1)
    finally:
        if app is not None:
            try:
                if not app._is_exiting:
                    app._tray_service.stop()
                    app._schedule_service.stop()
                    app._restore_startup_brightness()
            except Exception:
                logger.exception("Error during shutdown")
        lock.release()


if __name__ == "__main__":
    main()
