# EGA self-modifying-code investigation

The menu -> level-select artifact was investigated as a possible dynamic-code
problem: the game might patch a render routine after the intro/menu setup, while
our Python replacement still assumes the earlier static routine shape.

## Important detail

Comparing against the on-disk or initial loaded bytes is misleading.  The
unpacked EXE still performs an internal bootstrap/relocation stage and rewrites
large parts of `CS=1010h`.  For example, at the first timed boundary the bytes at
`1010:2750`, `1010:27EB`, `1010:2D2D`, `1010:CC90`, and `1010:5C00` are already
different from the raw load image.

The useful comparison is therefore:

1. run EGA until the first post-bootstrap timed/video boundary,
2. capture the live bytes as the baseline,
3. keep running through intro/menu/transition code,
4. report later modifications to the suspected render ranges.

## Diagnostic added

`python scripts/probe_ega_self_mod.py --boundaries 1200`

It watches:

- `1010:2750` EGA presenter,
- `1010:27D9..2990` EGA row/temp/mask pipeline,
- `1010:2D2D..2E40` mode-1 post-copy blitter,
- `1010:5C00..5D20` transition copier area,
- `1010:CC90..CD20` dirty-copy dispatcher,
- `1010:CD40..CE80` later transition/dispatch path,
- `1010:58DF..5905` post-copy wait loop.

Observed result over the intro/menu path: the suspected code ranges remain stable
after the first post-bootstrap baseline.  The only repeated change is
`1010:5901`, which is not an instruction body change; it is the inline variable
written by `1010:58E0`:

```asm
58DF  push cx
58E0  mov  cs:[5901],cx
```

So the current evidence does **not** support the idea that the EGA menu-mixing
bug is caused by the main EGA hooks executing stale pre-patch routine shapes.
The game absolutely patches/relocates code during bootstrap, but not later in the
watched EGA render routines during the tested path.

## Guardrail added

The EGA render/dirty hooks now have runtime entry-byte guards.  If the game ever
patches one of these routine entries in a future path, the hook removes itself
and leaves `CS:IP` at the original address so the interpreter executes the live
patched ASM on the next step.

Guarded hooks:

- `1010:2750`
- `1010:27EB`
- `1010:280D`
- `1010:2824`
- `1010:291C`
- `1010:2932`
- `1010:58DF`
- `1010:CCAA`
- `1010:CCC4`
- `1010:CCF0`

Set `OVERKILL_TRACE_CODE_PATCHES=1` to print when a hook self-disables because
its live entry bytes no longer match the post-bootstrap signature.

## Current conclusion

Self-modifying code is real during startup, but it is probably not the remaining
EGA screen-mixing cause.  The next more likely class of bugs is still EGA
page/present semantics: incomplete full-screen overwrite, page/source offset, or
more hardware-specific planar behavior not represented by the current simple
map-mask/read-plane emulation.
