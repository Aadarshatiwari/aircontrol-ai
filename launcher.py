"""PyInstaller entry point."""
from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()
    from aircontrol.ui import main

    raise SystemExit(main())
