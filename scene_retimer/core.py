"""Retiming maths and scene traversal.

The whole addon is built on one idea: a *piecewise-linear frame map*.  Every
retime range contributes one linear segment, and everything in the scene that
lives on the timeline is pushed through the same map.  That guarantees objects,
rigs, shape keys and markers stay in sync, because none of them are retimed
independently -- they all share one function.
"""

import re

from . import compat

# RET_<label>_start / RET_<label>_end, tag prefix supplied by the user.
# The legacy _1 / _2 suffixes are still accepted so existing scenes keep working.
_SUFFIX_RE = re.compile(r"^(?P<label>.+)[._-](?P<index>start|end|1|2)$",
                        re.IGNORECASE)

_INDEX_MAP = {"start": 1, "1": 1, "end": 2, "2": 2}

START_SUFFIX = "start"
END_SUFFIX = "end"


class RetimeRange:
    """One start/end marker pair plus the retime the user asked for."""

    def __init__(self, label, start, end):
        self.label = label
        self.start = start
        self.end = end
        self.new_duration = end - start
        self.ripple = True
        self.enabled = True
        self.objects = None  # None == whole scene, else a set of object names.

    @property
    def duration(self):
        return self.end - self.start

    @property
    def scale(self):
        if self.duration == 0:
            return 1.0
        return self.new_duration / self.duration

    @property
    def delta(self):
        return self.new_duration - self.duration


def parse_ranges(scene, prefix):
    """Build RetimeRange objects from tagged timeline markers.

    Returns (ranges, problems) where problems is a list of human-readable
    strings describing markers that could not be paired.
    """
    found = {}
    problems = []

    for marker in scene.timeline_markers:
        if not marker.name.startswith(prefix):
            continue
        remainder = marker.name[len(prefix):]
        match = _SUFFIX_RE.match(remainder)
        if not match:
            problems.append(
                "'%s' has the tag but no _start/_end suffix" % marker.name)
            continue
        label = match.group("label").strip("._-")
        index = _INDEX_MAP[match.group("index").lower()]
        slot = found.setdefault(label, {})
        if index in slot:
            problems.append("'%s' pair %d is defined twice" % (label, index))
            continue
        slot[index] = marker.frame

    ranges = []
    for label in sorted(found):
        slot = found[label]
        if 1 not in slot or 2 not in slot:
            missing = END_SUFFIX if 1 in slot else START_SUFFIX
            problems.append("'%s' is missing marker _%s" % (label, missing))
            continue
        start, end = sorted((slot[1], slot[2]))
        if start == end:
            problems.append("'%s' has zero length" % label)
            continue
        ranges.append(RetimeRange(label, start, end))

    ranges.sort(key=lambda r: r.start)

    # Overlaps would make the frame map ambiguous, so reject them outright.
    for previous, current in zip(ranges, ranges[1:]):
        if current.start < previous.end:
            problems.append(
                "'%s' overlaps '%s'" % (current.label, previous.label))

    return ranges, problems


def marker_names(prefix, label):
    """The names used when *creating* a new pair."""
    return ("%s%s_%s" % (prefix, label, START_SUFFIX),
            "%s%s_%s" % (prefix, label, END_SUFFIX))


def find_markers(scene, prefix, label):
    """Locate a label's two markers by parsing, not by rebuilding names.

    Necessary because a scene may hold legacy `_1` / `_2` markers alongside
    newly created `_start` / `_end` ones -- reconstructing the name would miss
    the old pairs entirely.
    """
    start = end = None
    for marker in scene.timeline_markers:
        if not marker.name.startswith(prefix):
            continue
        match = _SUFFIX_RE.match(marker.name[len(prefix):])
        if not match or match.group("label").strip("._-") != label:
            continue
        if _INDEX_MAP[match.group("index").lower()] == 1:
            start = marker
        else:
            end = marker
    return start, end


def has_overlap(ranges):
    return any(b.start < a.end for a, b in zip(ranges, ranges[1:]))


class FrameMap:
    """Piecewise-linear old-frame -> new-frame function for one set of ranges.

    Segments are stored as (start, end, scale, offset, ripple) in ascending
    order.  A frame inside a segment maps to
    `start + offset + (frame - start) * scale`; a frame after every segment
    just picks up the accumulated offset.
    """

    def __init__(self, ranges):
        self.segments = []
        offset = 0.0
        for retime in ranges:
            if not retime.enabled or retime.duration == 0:
                continue
            self.segments.append(
                (retime.start, retime.end, retime.scale, offset, retime.ripple))
            # A non-rippling range absorbs its own change; downstream keys stay put.
            if retime.ripple:
                offset += retime.delta

    @property
    def is_identity(self):
        return not self.segments

    def __call__(self, frame):
        trailing_offset = 0.0
        for start, end, scale, offset, ripple in self.segments:
            if frame < start:
                return frame + trailing_offset
            if frame <= end:
                return start + offset + (frame - start) * scale
            # A non-rippling segment absorbs its own stretch, so frames past it
            # only carry the offset inherited from earlier ranges.
            trailing_offset = offset + (end - start) * (scale - 1.0) if ripple \
                else offset
        return frame + trailing_offset


# --------------------------------------------------------------------------
# Scene traversal
# --------------------------------------------------------------------------

def _animdata_owners(obj):
    """Yield every ID hanging off an object that can carry its own action."""
    yield obj

    data = obj.data
    if data is not None:
        yield data
        shape_keys = getattr(data, "shape_keys", None)
        if shape_keys is not None:
            yield shape_keys

    for slot in obj.material_slots:
        material = slot.material
        if material is None:
            continue
        yield material
        if material.node_tree is not None:
            yield material.node_tree

    for system in getattr(obj, "particle_systems", []):
        if system.settings is not None:
            yield system.settings


def collect_actions(scene, objects=None):
    """Return the Actions that should have their keyframes remapped.

    Two categories are deliberately excluded:

    * **Driver F-Curves** -- a driver curve's X axis is the driver *input
      value*, not time. Remapping those would silently corrupt every driver.
    * **Actions owned by NLA strips** -- a strip maps scene time onto
      action-local time itself, so the strip is what gets stretched. Remapping
      the action as well would transform it twice, and an action shared by
      several strips at different times has no single correct remap at all.
    """
    actions = set()
    holders = []

    if objects is None:
        holders.extend(scene.objects)
        holders.append(scene)
        if scene.world is not None:
            holders.append(scene.world)
            world_nodes = getattr(scene.world, "node_tree", None)
            if world_nodes is not None:
                holders.append(world_nodes)
        # Scene.node_tree (compositor) was removed in Blender 5.x.
        compositor = getattr(scene, "node_tree", None)
        if compositor is not None:
            holders.append(compositor)
    else:
        holders.extend(objects)

    expanded = []
    for holder in holders:
        if hasattr(holder, "material_slots"):
            expanded.extend(_animdata_owners(holder))
        else:
            expanded.append(holder)

    nla_owned = set()
    for holder in expanded:
        anim = getattr(holder, "animation_data", None)
        if anim is None:
            continue
        if anim.action is not None:
            actions.add(anim.action)
        for track in anim.nla_tracks:
            for strip in track.strips:
                if strip.action is not None:
                    nla_owned.add(strip.action)

    # An action that is both directly assigned and stashed in a strip must not
    # be remapped -- the strip would then play a doubly-transformed action.
    return actions - nla_owned


def collect_nla_strips(scene, objects=None):
    sources = list(scene.objects) if objects is None else list(objects)
    strips = []
    for obj in sources:
        for holder in _animdata_owners(obj):
            anim = getattr(holder, "animation_data", None)
            if anim is None:
                continue
            for track in anim.nla_tracks:
                strips.extend(track.strips)
    return strips


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------

def remap_action(action, frame_map):
    """Remap every keyframe (and its bezier handles) in an action."""
    touched = 0
    for fcurve in compat.iter_fcurves(action):
        for key in fcurve.keyframe_points:
            old_x = key.co.x
            new_x = frame_map(old_x)
            # Handles are remapped through the same function so eases survive a
            # non-uniform scale instead of being stretched by a single factor.
            key.handle_left.x = frame_map(key.handle_left.x)
            key.handle_right.x = frame_map(key.handle_right.x)
            key.co.x = new_x
            if old_x != new_x:
                touched += 1
        fcurve.update()
    return touched


def remap_grease_pencil(obj, frame_map):
    data = obj.data
    touched = 0
    for layer in compat.gp_layers(data):
        frames = getattr(layer, "frames", None)
        if frames is None:
            continue
        # Sort descending when stretching so frames never collide mid-write.
        ordered = sorted(frames, key=lambda f: f.frame_number, reverse=True)
        for frame in ordered:
            new_number = int(round(frame_map(frame.frame_number)))
            if new_number != frame.frame_number:
                frame.frame_number = new_number
                touched += 1
    return touched


def remap_markers(scene, frame_map):
    touched = 0
    for marker in scene.timeline_markers:
        new_frame = int(round(frame_map(marker.frame)))
        if new_frame != marker.frame:
            marker.frame = new_frame
            touched += 1
    return touched


def remap_nla_strips(strips, frame_map):
    """Stretch NLA strips in scene time, leaving their actions alone.

    A strip already maps scene time onto action-local time, so retiming means
    moving its boundaries and adjusting `scale` to match. The action inside is
    never touched (see `collect_actions`).
    """
    touched = 0
    for strip in strips:
        # Transitions and meta strips are defined by their neighbours; moving
        # them directly either fails or corrupts the track.
        if getattr(strip, "type", "CLIP") != "CLIP":
            continue
        try:
            old_start, old_end = strip.frame_start, strip.frame_end
            new_start = frame_map(old_start)
            new_end = frame_map(old_end)
            old_length = old_end - old_start
            new_length = new_end - new_start
            if old_length <= 0 or new_length <= 0:
                continue

            if abs(new_length - old_length) > 1e-6:
                # Scale carries the stretch; without it the strip would simply
                # play a longer window of the same action and run out of keys.
                strip.scale = strip.scale * (new_length / old_length)

            # Widen before moving when growing, so Blender's own clamping
            # between frame_start and frame_end never truncates the write.
            if new_start >= old_start:
                strip.frame_end = max(new_end, strip.frame_end)
                strip.frame_start = new_start
                strip.frame_end = new_end
            else:
                strip.frame_start = new_start
                strip.frame_end = new_end
            touched += 1
        except (AttributeError, RuntimeError):
            continue
    return touched
