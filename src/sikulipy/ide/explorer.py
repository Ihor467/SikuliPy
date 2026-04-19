"""Script explorer — data model for the IDE's left-pane tree.

Port of ``org.sikuli.ide.ScriptExplorer``. This module is intentionally
headless: it returns a tree of :class:`ScriptTreeNode` instances that a
Flet view renders. Keeping the model separate from the widget layer
means we can unit-test the tree logic (which is where the interesting
bugs live) without spinning up Flet.

Recognised node kinds:

* ``"dir"``     — plain folder (traversed recursively)
* ``"bundle"``  — a SikuliX ``foo.sikuli`` folder (treated as a leaf)
* ``"script"``  — a standalone script file (``.py``, ``.rb``, ``.js``,
  ``.robot``, ...)
* ``"image"``   — a pattern image inside a bundle (``.png``, ``.jpg``, ...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

NodeKind = Literal["dir", "bundle", "script", "image"]


SCRIPT_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".rb", ".js", ".robot", ".ps1", ".sh", ".bash",
    ".applescript", ".scpt", ".script",
})
IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp",
})


@dataclass
class ScriptTreeNode:
    """One node in the script tree.

    ``path`` is absolute. ``name`` is the display label (file or folder
    basename for all node kinds). ``children`` is always empty for leaf
    kinds (``"script"``, ``"image"``, and ``"bundle"``).
    """

    path: Path
    name: str
    kind: NodeKind
    children: list["ScriptTreeNode"] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return self.kind != "dir"

    def iter_descendants(self) -> "list[ScriptTreeNode]":
        """Flat pre-order traversal (self first)."""
        out = [self]
        for c in self.children:
            out.extend(c.iter_descendants())
        return out

    def find(self, path: Path) -> "ScriptTreeNode | None":
        target = path.resolve()
        for node in self.iter_descendants():
            if node.path == target:
                return node
        return None


def classify(path: Path) -> NodeKind | None:
    """Return the node kind for ``path`` or ``None`` to skip it."""
    if path.is_dir():
        if path.suffix.lower() == ".sikuli":
            return "bundle"
        return "dir"
    ext = path.suffix.lower()
    if ext in SCRIPT_EXTENSIONS:
        return "script"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return None


def build_tree(
    root: str | Path,
    *,
    include_images: bool = True,
    include_hidden: bool = False,
) -> ScriptTreeNode:
    """Build an explorer tree rooted at ``root``.

    Bundles (``*.sikuli``) are returned as leaves — the IDE opens them as
    a single script rather than exposing their internals — unless
    ``include_images`` is ``True``, in which case bundled images are
    listed as ``"image"`` leaves under the bundle node.
    """
    root_path = Path(root).resolve()
    if not root_path.exists():
        raise FileNotFoundError(root_path)
    if not root_path.is_dir():
        raise NotADirectoryError(root_path)

    return _build(root_path, include_images=include_images, include_hidden=include_hidden)


def _build(
    path: Path, *, include_images: bool, include_hidden: bool
) -> ScriptTreeNode:
    kind = classify(path) or "dir"
    node = ScriptTreeNode(path=path, name=path.name or str(path), kind=kind)

    if kind == "bundle" and include_images:
        # Bundled images surface as children so the IDE sidebar can
        # enumerate them without a second walk.
        for child in _sorted_children(path, include_hidden=include_hidden):
            if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS:
                node.children.append(
                    ScriptTreeNode(path=child, name=child.name, kind="image")
                )
        return node

    if kind != "dir":
        return node

    for child in _sorted_children(path, include_hidden=include_hidden):
        child_kind = classify(child)
        if child_kind is None:
            continue
        node.children.append(
            _build(child, include_images=include_images, include_hidden=include_hidden)
        )
    return node


def _sorted_children(path: Path, *, include_hidden: bool) -> list[Path]:
    try:
        entries = list(path.iterdir())
    except PermissionError:
        return []
    if not include_hidden:
        entries = [e for e in entries if not e.name.startswith(".")]
    # Directories first, then files, each alphabetised.
    entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
    return entries
