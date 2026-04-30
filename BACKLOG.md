# Backlog — future improvements

Loose, prioritised list of features and polish that aren't blocking
any current phase. New ideas land here; once an item is ready to be
worked on, lift it into [`ROADMAP.md`](ROADMAP.md) under a numbered
phase with the design + tests it needs.

Format: one bullet per item, with a one-line "why" so we don't lose
the motivation between the time it lands here and the time we pick
it up.

## IDE

- **Action-log level toggle in the status bar.** Add an off / action /
  verbose dropdown next to the lint chip, persisted via Flet
  `client_storage`. Sets the global `ActionLogger` level so users can
  silence the Console mid-run or crank it up to chase a flaky find.
  Originally listed under Phase 10 but deferred — the runtime path
  works without it (level defaults to `action` while a script is
  running, off otherwise).

## Out of bounds for now

(Add items here that came up but were explicitly rejected, with a
sentence on *why*, so the same idea doesn't get re-pitched in three
months.)
