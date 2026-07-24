# Scene Retimer

**Fix the pacing of a whole animated scene without re-animating it.**

You animated everything — characters, props, cameras, rigs — and the timing is
off. Scene Retimer lets you mark out chunks of the timeline, say how long each
chunk *should* be, and stretches or squashes them across **every animated thing
in the scene at once**, so nothing drifts out of sync.

Author: OEBS Studios · Version 1.0.0 · Blender 4.2 – 5.x

---

## The idea in one picture

You want frames 320–400 (an 80-frame beat) to last twice as long:

```
before   |---------|=========|-------------------|
        280       320       400                 600

after    |---------|===================|-------------------|
        280       320                 480                 680
                   ^ stretched to 160f   ^ everything after slid +80
```

Everything downstream keeps its own internal timing — it just moves. That's
**Ripple** mode, and it's on by default.

---

## Installing

1. Blender → `Edit > Preferences > Add-ons > Install from Disk…`
2. Pick `scene_retimer.zip`
3. Tick **Scene Retimer**

The panel appears in the sidebar (`N` key) under a **Retime** tab, in the
**Dope Sheet**, the **Graph Editor**, and the **3D Viewport**.

---

## How to use it

### 1. Mark out a range

**The two-click way (recommended).** Scrub to where the beat starts and press
**Initialize Range At 320**. That drops the opening marker and the panel flips
into build mode:

```
┌──────────────────────────────────────────┐
│ ⏺ Building 'range1'                  ✕   │
│   Opened at 320, now at 372 (52 frames)  │
│   [        ✔ Set Range End         ]     │
└──────────────────────────────────────────┘
```

Now scrub freely — the readout follows your playhead so you can watch the
length as you look for the right frame. When you land on it, press
**Set Range End**. The **✕** cancels and cleans up the orphan marker.

Scrubbing *backwards* is fine; the earlier frame always becomes the start.
Closing on the same frame you opened on is refused rather than making a
zero-length range.

There's also a **+** button next to it for the old dialog-based way (type both
frames at once), which is handy when you already know the numbers.

Either way you end up with two timeline markers:

```
RET_impact_start   at frame 320
RET_impact_end   at frame 400
```

You can also just make the markers by hand — the addon picks up **any** marker
pair that starts with the tag prefix (default `RET_`), shares a label, and ends
in `_start` and `_end`. Order doesn't matter; the earlier marker is always the start.

The tag prefix is editable at the top of the panel, so if you'd rather use
`rt.` or `TIME_`, go ahead.

### 2. Dial in the new timing

Every range in the scene is tracked in one list, with the active one's
settings below it:

```
┌──────────────────────────────────────┬───┐
│ ☑ 📍 impact      320-400      +80    │ ⌄ │  <- specials menu
│ ☑ 📍 anticip     410-460      -20 ⬚  │   │
│ ☐ 📍 settle      600-680       --    │   │
└──────────────────────────────────────┴───┘
┌──────────────────────────────────────────┐
│ 📍 impact              ◁  ▷  ▶           │
│   Start [ 320 ]     End [ 400 ]          │
│   80 frames long                         │
│   Frames [ 160 ]     Scale [ 2.000 ]     │
│   [ ⏩ Ripple ]  [ ⬚ Selected Only ]      │
└──────────────────────────────────────────┘
```

The list gives you the whole picture at a glance: bounds, the frame delta
(`+80`, `-20`, or `--` when unchanged), and small badges when a range is set
to no-ripple or Selected Only — so a range behaving oddly is visible without
clicking through each one.

- **Start / End sliders** — drag either slider to move the actual timeline
  marker. The range retargets instantly, preserving your scale intent.
- **Frames** and **Scale** are linked — type in either one and the other
  updates. Use Frames when you know the target length ("this beat needs to be
  160 frames"), Scale when you're speeding several things up uniformly.
- **☑ checkbox** — temporarily exclude a range without deleting its markers.
- **◁ / ▷** — select just the start or end marker. Essential when two
  ranges overlap and you can't click the right marker in the timeline.
- **▶** — jumps the playhead and sets the preview range to this beat.

### Or just drag the markers

Press **Drag To Retime** and the markers become live handles:

```
armed at 320-400, then you drag the closing marker right:

 RET_beat_start                    RET_beat_end
     │                              │
     ▼                              ▼
 ────●══════════════════════════════●────────
    320        (source 320-400)    480
                                   └─ panel now reads 160 frames, x2.000
```

- **Drag the `_end` marker** → sets the new duration. The panel's Frames and
  Scale fields follow you live.
- **Drag the `_start` marker** → slides the whole range, keeping its duration.
- **Nothing is baked until you press Apply.** Dragging only moves the target,
  so you can shove it around freely and undo costs nothing.

The source range stays pinned at wherever it was when you armed the mode — the
panel keeps showing `Frames 320 - 400 (80 long)` while you drag, so you can
always see what you're stretching *from*. Dragging the closing marker back past
the opening one clamps at one frame instead of going negative.

After Apply, the markers land on the new timing and re-arm automatically, so
you can immediately drag again for another pass.

If you accidentally move the **start** marker while drag mode is on, a warning
box appears — because the addon can't tell whether you meant to slide the range
or relocate both markers. Use **Commit To New Range** (in the warning or the
specials menu) to adopt the current marker positions as the new source and reset
the scale to 1.0. This is also available any time from the specials menu (⌄) as
**Commit Active/All To New Range**.

### Moving markers retargets the range

Markers say *which section* you are working on. Drag either marker to a new
frame and the range follows — the addon retimes wherever the markers are now,
not where they used to be.

Your intent is preserved across the move. A range set to ×2 that you slide
from 320-400 onto 500-600 stays ×2 and retargets to 200 frames, rather than
resetting to 1.0 and making you re-type it:

```
before   [======= x2 =======]                       (320-400 -> 160)
markers moved to a different beat:
after                          [======= x2 =======] (500-600 -> 200)
```

The one exception is while **Drag To Retime is armed**. There the closing
marker is a live retime handle parked at the target frame, so it can't also be
telling the addon where the range starts — dragging it changes duration
instead. Turning drag mode off then on again picks up any marker moves you
made in between and re-freezes the baseline where the markers actually are.

On Apply, the markers are parked back onto the source range before anything is
retimed, then carried to the new timing by the frame map — so afterwards they
always bound the retimed section exactly.

### The specials menu (⌄)

| Item | What it does |
|---|---|
| **Rename Range** | renames the range *and* both its markers |
| **Snap Markers To Keyframes** | moves the active range's markers onto the nearest existing keyframes |
| **Snap All To Keyframes** | same, for every range |
| **Enable / Disable All** | bulk-toggle the checkboxes |
| **Ripple All On / Off** | bulk-set ripple mode |
| **Selected Only: All On / Off** | bulk-set the selection filter |
| **Preview Range Covers All** | sets the preview range to span every retime range |
| **Reset All Values** | back to 1.0 scale everywhere |
| **Commit Active To New Range** | adopt current marker positions as the source, reset scale to 1.0 |
| **Commit All To New Range** | same, for every range |
| **Delete All Ranges** | removes every tagged marker pair (asks first) |

**Snap To Keyframes** is the one worth knowing about. If you eyeballed a marker
onto frame 320 but the pose actually lands on 322, the retime pivots two frames
off and you get a subtle drift. Snapping pulls the markers onto real keys so the
range lines up with the animation rather than with where you happened to click.

### 3. Apply

Press **Apply Retime**. The status bar reports how many keys, actions, markers,
Grease Pencil frames and NLA strips were moved.

The markers move with the animation, so after applying, your `impact` range now
reads 320–480 and is ready for another pass.

---

## The two mode toggles

### Ripple (on by default)

- **On** — everything after the range shifts by the change. The rest of your
  animation keeps its internal timing. This is what you want ~90% of the time.
- **Off** — only keys *inside* the range move. Frames after it stay exactly
  where they are. Useful when you're fitting a beat into a fixed slot, but
  watch out: if you stretch a range with ripple off, its keys can run past
  where the next section starts and overlap it.

### Selected Only

Limits that one range to the objects you have selected. Everything else in the
scene ignores it.

**Be careful with this one.** It is genuinely useful — "let just the camera
move slower through this section" — but it *will* desync that object from the
rest of the scene, because that's literally what you asked for. Scene-wide
ranges are applied first, then each filtered range runs as its own pass, so the
two never fight over the same keys.

---

## What gets retimed

Under **Affect:** in the panel:

| | |
|---|---|
| Object & rig actions | always — transforms, pose bones, constraints, custom props |
| Shape keys | always |
| Materials & node trees | always |
| Particle settings | always |
| **Untagged Markers** | other timeline markers slide along — **including camera-bound markers**, whose camera binding is preserved |
| **NLA Strips** | strips are stretched in scene time — see below |
| **Grease Pencil** | drawing frames are remapped |
| **Extend Scene Range** | grows `frame_end` if the animation got longer |

### How the NLA is handled

NLA has **two time spaces**: the strip lives in scene time, and the action
inside it lives in its own action-local time. The strip is the thing that maps
one onto the other.

So Scene Retimer stretches **the strip** and leaves **the action inside it
completely untouched**:

```
before   strip 320-400   scale 1.0   action keys 320-400
after    strip 320-480   scale 2.0   action keys 320-400  (unchanged)
```

The strip's `scale` absorbs the retime. That's what makes it correct, and it
has two consequences worth knowing:

- **Actions in the NLA are never keyframe-remapped**, even when they're also
  assigned directly to an object. Retiming both the strip *and* its contents
  would transform the animation twice — the strip would end up playing a
  window that no longer matches the keys inside it.
- **A shared action is safe.** If the same action is used by five strips at
  five different points on the timeline, there is no single correct way to
  remap its keys. Each strip is moved and scaled independently instead, which
  is the only answer that works for all five.

Strips *downstream* of a retimed range slide by the delta without being
stretched, keeping their own internal timing — the same ripple rule as
everything else.

Transition and meta strips are skipped, since they're defined by their
neighbours and move automatically.

### What is deliberately *not* touched

**Drivers.** A driver F-Curve's horizontal axis is the driver's *input value*,
not time. Remapping those would silently corrupt every driver in your file. So
Scene Retimer skips them entirely — and there's a regression test that fails if
that ever changes.

---

## Notes and gotchas

- **Ranges may not overlap.** The frame map would be ambiguous, so Apply
  refuses and tells you which two collide. Butting them end-to-end is fine.
- **This edits keyframes destructively.** Undo works, but on a heavy scene,
  save first. Old habits.
- **Bezier handles** are remapped through the same function as the keys, so
  your eases survive a stretch instead of being flattened.
- **Grease Pencil frames are integers**, so extreme squashes can merge two
  drawings onto the same frame. Blender's rounding, not much to do about it.
- Marker problems (a `_start` with no `_end`, a duplicate, a zero-length range) are
  listed in a warning box in the panel rather than failing silently.
- **Camera markers** are handled: a cut sitting inside a retimed beat moves
  *proportionally*, so it stays at the same moment in the performance rather
  than the same frame number. Cuts downstream ripple by the full amount.

---

## Verification

Tested headless on **Blender 5.1.1**, 149/149 checks passing across nine suites.

Core suite (23) — frame-map maths,
ripple and no-ripple modes, multi-range offset accumulation, marker parsing and
error reporting, end-to-end object + armature retiming, the linked
Frames/Scale fields, marker follow-through, and the drivers-untouched
guarantee.

Camera-marker suite (10) — upstream markers held still, in-range camera cuts
stretched proportionally, downstream cuts rippled, `.camera` bindings preserved
through the retime, tag markers tracking their new bounds, and the
**Untagged Markers** opt-out honoured.

Interface suite (29) — the two-click builder including backwards scrubbing,
same-frame rejection and cancel cleanup; UIList and menu registration; every
specials-menu operator (rename with value carry-over and duplicate rejection,
bulk flags, keyframe snapping, preview range, delete all); and a full retime
run afterwards to confirm the builder feeds the core correctly.

Drag suite (24) — baseline freezing on arm, both drag gestures, reverse-drag
clamping, squash as well as stretch, apply-while-armed producing correct keys
*without* double-moving the dragged marker, automatic re-baselining, a second
drag/apply cycle, and timer teardown on disarm and unregister.

NLA suite (14) — strips stretched with a compensating `scale`, actions inside
strips left byte-identical, `action_frame` windows preserved, downstream strips
rippled without stretching, directly-animated objects still retimed alongside,
an action shared by two strips remapped by neither, and the **NLA Strips**
opt-out honoured.

Baseline suite (18) — new pairs created as `_start`/`_end`, legacy `_1`/`_2`
markers still parsed and removable, moving markers retargets the range while
preserving scale intent, Apply retimes the new area, dragging `_end` under
drag mode changes duration without moving the source, arming drag mode after
a hand-move freezes the baseline on the NEW area (the reported 1→0.7 fix).

Select-marker suite (5) — select start/end markers including legacy `_1`/`_2`.

Handle-slider suite (14) — slider read/write, retargeting with scale
preservation, external marker moves reflected, legacy markers drivable,
drag mode compatibility, missing marker safety.

Commit suite (14) — both-markers-moved detection, end-only move not
suspicious, commit resets source and scale, flag cleared after commit,
no false positives with drag mode off, start-slide-only detection.
