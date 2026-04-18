"""Code editor component — Phase 7.

Ports the behaviour of EditorPane.java + SikuliEditorKit.java + EditorViewFactory.java:
syntax highlighting, inline pattern buttons (image references rendered as
clickable thumbnails in the source), line numbers, and undo/redo.

For the first pass we wrap ``flet.TextField`` (multiline) and add a
very small syntax hint overlay. Rich inline image rendering will come
later — Flet does not have a first-class inline-image-in-text widget,
so we may migrate to a code-mirror-in-iframe approach.
"""
