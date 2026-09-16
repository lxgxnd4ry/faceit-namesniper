"""
Namesniper - Faceit Name Checker
Main Entry Point

Usage:
  python main.py         -> Launches Desktop GUI (Edge Chromium / pywebview)
  python main.py --cli   -> Launches Terminal CLI
  python main.py --help  -> Shows CLI options
"""
import sys
import argparse

def _attach_console_if_needed():
    if sys.platform == "win32":
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8")
                sys.stderr = open("CONOUT$", "w", encoding="utf-8")
        except Exception:
            pass

def main():
    # If any CLI arguments are passed (other than just --gui), check if user requested CLI
    if len(sys.argv) > 1:
        if "--cli" in sys.argv or "-c" in sys.argv:
            _attach_console_if_needed()
            sys.argv = [arg for arg in sys.argv if arg not in ("--cli", "-c")]
            from cli import run_cli
            run_cli()
            return
        elif "--help" in sys.argv or "-h" in sys.argv or "--stats" in sys.argv or "--test-key" in sys.argv:
            _attach_console_if_needed()
            from cli import run_cli
            run_cli()
            return
        elif "--gui" in sys.argv:
            from gui import launch_gui
            launch_gui()
            return
        else:
            # Arguments like -w, -t, etc. were provided -> run CLI
            from cli import run_cli
            run_cli()
            return

    # Default: launch Desktop GUI, with fallback to CLI if pywebview window fails
    try:
        from gui import launch_gui
        launch_gui()
    except Exception as e:
        print(f"Failed to initialize Desktop GUI: {e}")
        print("Falling back to Terminal CLI mode...\n")
        from cli import run_cli
        run_cli()

if __name__ == "__main__":
    main()
