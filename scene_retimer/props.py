"""Scene-level properties. Per-range settings persist in the .blend."""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

# Guard so the linked duration/scale fields don't update each other forever.
_updating = False


def _marker_frame(item, which):
    """Look up one of this range's two markers and return its frame, or 0."""
    from . import core
    scene = item.id_data
    prefix = scene.scene_retimer.prefix
    start, end = core.find_markers(scene, prefix, item.label)
    marker = start if which == "start" else end
    return marker.frame if marker is not None else 0


def _move_marker(item, which, value):
    """Move a marker and let sync_ranges retarget the range."""
    from . import core, ops as sr_ops
    scene = item.id_data
    prefix = scene.scene_retimer.prefix
    start, end = core.find_markers(scene, prefix, item.label)
    marker = start if which == "start" else end
    if marker is None or marker.frame == value:
        return
    marker.frame = value
    # In drag mode the timer picks the move up; otherwise sync now so the
    # panel and any downstream retime numbers update straight away.
    if not scene.scene_retimer.drag_mode:
        sr_ops.sync_ranges(scene)


def _handle_start_get(self):
    return _marker_frame(self, "start")


def _handle_start_set(self, value):
    _move_marker(self, "start", value)


def _handle_end_get(self):
    return _marker_frame(self, "end")


def _handle_end_set(self, value):
    _move_marker(self, "end", value)


def _duration_updated(self, context):
    global _updating
    if _updating:
        return
    _updating = True
    try:
        if self.orig_duration > 0:
            self.scale = self.new_duration / self.orig_duration
    finally:
        _updating = False


def _scale_updated(self, context):
    global _updating
    if _updating:
        return
    _updating = True
    try:
        new_duration = max(1, int(round(self.orig_duration * self.scale)))
        self.new_duration = new_duration
    finally:
        _updating = False


def _drag_mode_toggled(self, context):
    # Imported here to avoid a circular import at module load.
    from . import drag, ops as sr_ops
    if self.drag_mode:
        # Pick up any marker moves made while drag mode was off, so the
        # baseline drag then freezes matches where the markers actually are.
        # Without this, arming right after moving markers would freeze the
        # STALE baseline and the retime would read as some spurious scale.
        sr_ops.sync_ranges(context.scene)
        drag.arm(context.scene)
    else:
        drag.disarm(context.scene)


class SR_RetimeItem(PropertyGroup):
    """UI state for one marker pair. Rebuilt from markers, settings preserved."""

    label: StringProperty(name="Label")
    orig_start: IntProperty(name="Start")
    orig_end: IntProperty(name="End")
    orig_duration: IntProperty(name="Original Duration", default=1)

    # Frozen marker positions while drag mode is armed. Without these the
    # baseline would follow the marker being dragged and the retime would
    # always read as 1.0.
    base_start: IntProperty()
    base_end: IntProperty()
    start_was_dragged: BoolProperty(default=False)

    # Live handles: reading gets the marker's current frame, writing moves it.
    # No storage of their own -- always in sync with the actual markers.
    handle_start: IntProperty(
        name="Start", description="Frame of this range's start marker",
        get=_handle_start_get, set=_handle_start_set,
    )
    handle_end: IntProperty(
        name="End", description="Frame of this range's end marker",
        get=_handle_end_get, set=_handle_end_set,
    )

    new_duration: IntProperty(
        name="New Duration",
        description="Target length of this range in frames",
        default=1,
        min=1,
        soft_max=2000,
        update=_duration_updated,
    )
    scale: FloatProperty(
        name="Scale",
        description="Time multiplier. 2.0 is twice as slow, 0.5 twice as fast",
        default=1.0,
        min=0.01,
        soft_max=10.0,
        precision=3,
        update=_scale_updated,
    )

    enabled: BoolProperty(
        name="Enabled",
        description="Include this range when applying",
        default=True,
    )
    ripple: BoolProperty(
        name="Ripple",
        description=(
            "Shift every keyframe after this range so the rest of the "
            "animation keeps its timing. Disable to retime in place"
        ),
        default=True,
    )
    use_selection: BoolProperty(
        name="Selected Only",
        description=(
            "Limit this range to the selected objects instead of the whole "
            "scene. Note: mixing filtered and unfiltered ranges can desync "
            "objects, so it is applied as a separate pass"
        ),
        default=False,
    )


class SR_Settings(PropertyGroup):
    prefix: StringProperty(
        name="Tag Prefix",
        description=(
            "Marker name prefix that identifies retime markers. Pair them by "
            "giving both markers the same label and a _1 / _2 suffix, e.g. "
            "RET_impact_1 and RET_impact_2"
        ),
        default="RET_",
    )
    ranges: CollectionProperty(type=SR_RetimeItem)
    active_index: IntProperty(default=0)

    # Two-click range building. Non-empty pending_label means the opening
    # marker is down and we are waiting for the user to scrub and close it.
    pending_label: StringProperty(default="")
    pending_frame: IntProperty(default=0)

    drag_mode: BoolProperty(
        name="Drag To Retime",
        description=(
            "Turn the closing marker of each range into a live handle. Drag it "
            "in the timeline to set the new duration; drag the opening marker "
            "to slide the whole range. Nothing is baked until you press Apply"
        ),
        default=False,
        update=_drag_mode_toggled,
    )

    include_markers: BoolProperty(
        name="Untagged Markers",
        description="Move other timeline markers along with the animation",
        default=True,
    )
    include_nla: BoolProperty(
        name="NLA Strips",
        description="Retime NLA strip boundaries",
        default=True,
    )
    include_gpencil: BoolProperty(
        name="Grease Pencil",
        description="Retime Grease Pencil drawing frames",
        default=True,
    )
    adjust_scene_range: BoolProperty(
        name="Extend Scene Range",
        description="Grow the scene end frame if the animation gets longer",
        default=True,
    )


classes = (SR_RetimeItem, SR_Settings)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.scene_retimer = bpy.props.PointerProperty(type=SR_Settings)


def unregister():
    del bpy.types.Scene.scene_retimer
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
