"""Command-line entry point.

Mirrors the ``sikulix`` and ``oculix`` launchers from the Java project.
Currently only exposes ``ide`` and ``version`` subcommands.
"""

from __future__ import annotations

import typer

from sikulipy import __version__

app = typer.Typer(add_completion=False, help="SikuliPy — visual automation toolkit.")


@app.command()
def version() -> None:
    """Print the SikuliPy version."""
    typer.echo(f"SikuliPy {__version__}")


@app.command()
def ide() -> None:
    """Launch the Flet-based IDE."""
    from sikulipy.ide.app import main

    main()


@app.command()
def run(script: str) -> None:  # noqa: ARG001 - stub
    """Run an automation script (stub)."""
    raise NotImplementedError("Script runner not implemented yet — see ROADMAP.md Phase 6.")


if __name__ == "__main__":
    app()
