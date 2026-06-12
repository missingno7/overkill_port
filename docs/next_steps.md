# Next engineering steps

1. Decode the hot self-modified expansion routine at `1010:45CB` / `1010:45CE`. It dominates current startup runtime and is the best next replacement target.
2. Use the locally generated `artifacts/evidence/snapshot_after_bootstrap_100k/memory_1mb.bin` snapshot, or whichever fresh bootstrap snapshot you just produced, as the authoritative binary image for addresses that differ from `assets/OVERKILL.UNLZEXE.EXE`.
3. Add a symbolic trace annotator that reads `symbols.json` and appends names to trace lines.
4. Add an executed-address coverage report: runtime `CS:IP` -> physical address -> load-module offset when possible -> symbol name.
5. Add a VGA memory watcher for writes to `A000:` and text/video BIOS effects, so we can tell when startup begins drawing recognizable screens.
6. Keep implementing only instructions actually encountered, with tests for each new group.
7. Once the first menu/game loop is reached, split hardware into explicit subsystems: video, keyboard, timer, sound, file/resource IO.
8. Compare selected traces against DOSBox-X/Spice86 once the same checkpoint can be captured there.
