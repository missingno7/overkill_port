# Campaign: AUDIO (tier: EVENT-exact → AdLib/OPL3 music)

**Scope.** The BEFF sound queue (the walk already writes the right events: 0x0B spawn, 0x0F hit,
0x19 explosion, 0x1A shot...) → a host mixer playing the right sound at the right event, AND the
AdLib/OPL3 **music** driven by the game's own YM3812 register stream.

**Done when:** the queued events + the music audibly play in play_native, verified against the VM's
own OPL register stream (the audio oracle).

## State (2026-07-11)

**Pipeline PROVEN + oracle tool landed.** `scripts/render_demo_music.py` replays a demo through the
ref VM, captures the game's per-frame OPL register writes (`dos.set_adlib_callback` — the VM
intercepts the 388h/389h port writes from the loaded AdLib driver at segment 2032), and synthesizes
them through dos_re's **`pynuked_opl3`** (Nuked-OPL3, already built + available) into a stereo WAV.
A 40s cold-start render is full, correct intro/menu music (peak 26682, mostly non-silent).  This is
the AUDIO ORACLE: the byte-faithful reference the live path is checked against.

**Key facts established:**
- `pynuked_opl3.OPL3` (dos_re) is available: `write(reg,val)`, `generate_stereo(n)`, `OPL_NATIVE_RATE`.
- dos_re's `AdlibSpeakerSink` (`dos_re/dos_re/audio_sink.py`) is the live sink: OPL callback +
  PC-speaker square wave → pygame mixer, `present_hz=60`, `rate/60` samples/frame.
- **native_frame already runs the D50E sound engine each frame** (`_sound_engine_tick_d50e`): the
  [BEFF] queue → D566 effect start, the [BF00] beat, the channel cells (BFB0/BFB3 PC-speaker,
  BFB5/BFC5/BFB8/BFC8).  So play_native's image carries the live sound-engine state.
- **The AdLib driver is present in the image at segment 2032** ("Type : AdLib" header, tick
  `2032:0063`, YM3812 register write `2032:0557`).  It is real 8086 code, recovered only as
  VM-coupled hooks (`overkill/sounds/adlib_driver.py`, which fall back to `_run_original_near`), so
  it CANNOT run standalone — it needs a CPU.

## The live design (the co-processor)

play_native stays VM-less for GAMEPLAY; AUDIO is a host concern layered on top, exactly like the
PC-speaker `SpeakerSink`.  A minimal dos_re **sound co-processor** runs the real AdLib driver over the
sound state native_frame maintains:

1. Boot a dos_re runtime with the AdLib command tail once; advance it until the driver is initialised
   and it is in gameplay (the driver's instrument/sequencer state is ready in segment 2032).
2. Each play_native frame: sync the D50E sound-state DGROUP region (the driver's INPUT) from
   play_native's image into the co-processor, then run the driver tick `2032:0063` the right number of
   times per frame (tempo = the PIT music rate the driver programs).
3. Capture the OPL writes via `dos.set_adlib_callback` → feed `AdlibSpeakerSink`/`pynuked_opl3`.

**Open unknowns to resolve before implementing (all bounded):**
- The exact D50E↔driver interface: which DGROUP cells the driver READS (its input) vs. keeps private
  in segment 2032 — so the sync copies input only, avoiding double-processing D50E.
- Driver init: the static bundle boots Tandy/PC-speaker; the co-processor must boot AdLib so 2032 is
  initialised.
- Tempo: driver ticks per present-frame (the PIT rate the driver sets vs. the 60 Hz present).
- **Verification:** the co-processor's OPL stream on a demo must match `render_demo_music.py`'s VM
  capture (same demo, same registers) — that is the audio oracle gate.

Until the co-processor lands, `render_demo_music.py` produces the reference music per demo (and can
back an attract-mode music bed).  PC-speaker SFX already play live via `SpeakerSink`.

## DECISION (2026-07-11): VM-FREE DRIVER RECOVERY (owner's call)

Not a shadow VM -- recover the segment-2032 AdLib driver as pure Python (true to the VM-less
principle), verified against the `render_demo_music.py` oracle.  Scaffolding landed:
`overkill/native_audio/adlib.py` (`AdlibDriver`: the segment-2032 state image + the emitted YM3812
`(reg,val)` stream) with the leaf `2032:0557` (register write) transcribed + unit-tested
(`tests/test_native_adlib.py`).

**Enablers confirmed:**
- The driver code is NOT in `boot_1010_entry` (that image is PC-speaker; 2032:0557 is zeros).  Seed
  the driver state from an **AdLib** snapshot -- `demo_play_tandy_20260711_120636/snapshot` has it
  (2032:0557 == `SIG_ADLIB_WRITE_2032_0557`).
- `overkill/sounds/adlib_driver.py` is the LIFTED reference (VM-coupled hooks, interpreter-verified) --
  transcribe each to operate on `AdlibDriver.ram`/DGROUP instead of `cpu`.
- Oracle = `render_demo_music.py`'s per-frame VM OPL capture; the gate diffs the VM-free driver's
  `(reg,val)` stream against it over an AdLib demo.

**Slice order (each: transcribe from the lifted hook, diff OPL vs the oracle, commit):**
1. `2032:0557` write leaf ✅ (done).
2. `2032:0579` PIT delay (host no-op) + `2032:04E9` detect (init path).
3. `2032:0063` tick spine ✅ (done) + `2032:0409` page gate / pattern loader ✅ (done 2026-07-11:
   the full loader -- `0291` sequencer-silence + `04A4` operator-reset + the page-descriptor load that
   sets `[000C]`/`[0060]` and each channel's bytecode pointer + the BD/08 arm; tested structurally +
   differentially vs the `demo_play_tandy_20260711_120636` snapshot's own active page).
4. `2032:00CD` per-channel bytecode sequencer -- the last VM-coupled piece.  The lifted
   `run_adlib_channel_tick_2032_00cd` fast-paths the idle case and defers the command-advance path
   (`00F7` loop) to the interpreter; transcribe that command loop, dispatching to the ALREADY-lifted
   `0181` set-instrument, `024F` note/frequency, `0244`/`02AA` helpers and `02C9`/`02F6` mod A/B
   (transcribe each from the lifted hook onto `AdlibDriver.ram`).
5. THE ORACLE GATE: seed `AdlibDriver` from an AdLib snapshot's segment 2032, run `tick_2032_0063`
   the right number of times per present-frame over an AdLib demo, and diff its `(reg,val)` stream
   against `render_demo_music.py`'s per-frame VM capture -- byte-exact.  (Resolve the ticks-per-frame
   and the game->driver input-cell interface here.)
6. Wire `AdlibDriver` into play_native each frame over the D50E sound state -> `AdlibSpeakerSink`/
   `pynuked_opl3`; full-demo OPL diff vs the oracle must be zero.
