"""Legacy cartopy smoke test — prefer `versusworld preview`."""

from versusworld.cli import app

if __name__ == "__main__":
    # Delegate to CLI preview for a real World Versus render
    import sys

    sys.argv = ["versusworld", "preview"]
    app()
