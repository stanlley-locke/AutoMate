"""AutoMate Application Entrypoint for Windows Desktop & Standalone Binary.

When launched without command-line arguments (e.g. from desktop or Start menu shortcut),
opens the modern graphical user interface. When arguments are supplied (e.g. automate run ...),
invokes the CLI command engine.
"""

import sys
import os

# Ensure Windows DPI awareness before GUI initialization
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from automate.cli import main
        main()
    else:
        from automate.ui import launch_ui
        launch_ui()
