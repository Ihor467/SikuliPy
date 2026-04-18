"""Session-level pytest configuration.

On hosts whose CPU predates x86-64-v2, NumPy 2.x refuses to load. Individual
test modules use ``pytest.importorskip("numpy")`` at the top to self-skip;
this conftest exists mainly to anchor the test package.
"""

from __future__ import annotations
