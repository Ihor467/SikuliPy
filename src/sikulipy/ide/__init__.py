"""Flet-based IDE — replaces the Swing IDE from the Java project.

Ports the high-level concepts of OculiX/IDE/src/main/java/org/sikuli/ide:
* EditorPane             -> central code editor (:mod:`.editor`)
* ScriptExplorer         -> left file tree (:mod:`.explorer`)
* SikuliIDEStatusBar     -> bottom status bar (:mod:`.statusbar`)
* EditorConsolePane      -> bottom console (:mod:`.console`)
* ButtonCapture / Run    -> toolbar actions (:mod:`.toolbar`)
* OculixSidebar          -> right sidebar with captured patterns (:mod:`.sidebar`)
"""
