"""Template for ``tests/web/conftest.py`` written by Web Auto codegen.

The generated conftest declares two pieces the Page Object base class
expects to find on the test session:

* ``--update-baselines`` — pytest CLI flag that flips baseline writes
  from ``raise FileNotFoundError`` to ``promote_from`` the captured
  frame. Wire it through ``BaselineStore`` in your own test if you
  promote frames at runtime; the flag is exposed here so every
  generated suite uses the same incantation.
* ``web_screen`` — the fixture every Page Object subclass takes as
  its first ctor argument. Default implementation spins a real
  :class:`sikulipy.web.screen.WebScreen` with the recorded URL; tests
  that want a stubbed screen override this fixture in a per-module
  ``conftest.py``.

Generated as a *template*: written once per project, then owned by
the user. Re-running the IDE's "Generate tests" button will not
overwrite an existing conftest.
"""

from __future__ import annotations


CONFTEST_SOURCE = '''\
"""Auto-generated test session config for Web Auto suites.

Owns the ``--update-baselines`` flag and the ``web_screen`` /
``project_dir`` fixtures every generated Page Object expects. Edit by
hand — re-running Generate tests in the IDE skips this file when it
already exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-baselines",
        action="store_true",
        default=False,
        help="Promote the current frame to the baseline store on miss",
    )


@pytest.fixture(scope="session")
def update_baselines(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--update-baselines"))


@pytest.fixture(scope="session")
def project_dir() -> Path:
    """Directory baselines + assets live under (repo root by default)."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def web_screen(project_dir: Path):
    """Real Playwright-backed screen. Override per-module to stub."""
    from sikulipy.web.screen import WebScreen

    screen = WebScreen()
    yield screen
    screen.close()
'''
"""Default contents written to ``tests/web/conftest.py`` by the IDE
codegen. Kept as a module-level string so callers don't have to read
a packaged data file."""
