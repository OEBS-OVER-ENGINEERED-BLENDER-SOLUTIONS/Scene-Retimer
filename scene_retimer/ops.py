"""Operators: build marker pairs, sync the list, and apply the retime."""

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Operator

from . import compat, core


def _settings(context):
    return context.scene.scene_retimer


def sync_ranges(scene, rebaseline=False):
    """Rebuild the UI list from the markers, keeping per-label settings.

    Markers say *which section* you are working on, so moving them normally
    retargets the range -- drag one pair onto a different beat and that beat is
    what gets retimed. What is preserved across the move is your *intent*: a
    range set to x2 stays x2 against the new bounds rather than resetting.

    The one exception is while **drag mode is armed**. There the closing marker
    is a live retime handle parked at the target frame, so the frozen baseline
    must win -- otherwise the source range would chase the handle and the
    retime would always read as x1.

    `rebaseline=True` additionally resets every range to neutral. Used right
    after an Apply, when the frame map has just moved the markers onto the new
    timing and the retime is spent.
    """
    settings = scene.scene_retimer
    ranges, problems = core.parse_ranges(scene, settings.prefix)

    remembered = {
        item.label: (item.new_duration, item.scale, item.enabled,
                     item.ripple, item.use_selection, item.orig_duration,
                     item.base_start, item.base_end)
        for item in settings.ranges
    }

    settings.ranges.clear()
    for retime in ranges:
        item = settings.ranges.add()
        item.label = retime.label
        previous = remembered.get(retime.label)

        # While drag mode is armed the closing marker is a handle, not a
        # boundary, so the frozen baseline wins. Otherwise the markers say
        # where the range is and they win.
        hold_baseline = (settings.drag_mode and previous is not None
                         and not rebaseline)
        if hold_baseline:
            item.base_start, item.base_end = previous[6], previous[7]
        else:
            item.base_start, item.base_end = retime.start, retime.end

        item.orig_start = item.base_start
        item.orig_end = item.base_end
        # orig_duration must be written before new_duration so the linked
        # Scale field derives from the right baseline.
        item.orig_duration = max(1, item.base_end - item.base_start)

        if previous is None or rebaseline:
            item.new_duration = item.orig_duration
            item.scale = 1.0
            if previous is not None:
                item.enabled, item.ripple, item.use_selection = previous[2:5]
        else:
            item.enabled, item.ripple, item.use_selection = previous[2:5]
            if hold_baseline:
                item.new_duration, item.scale = previous[0], previous[1]
            else:
                # Markers moved: keep the ratio the user asked for, retargeted
                # onto the new bounds, instead of throwing their value away.
                item.new_duration = max(
                    1, int(round(item.orig_duration * previous[1])))

    settings.active_index = min(
        settings.active_index, max(0, len(settings.ranges) - 1))

    # Rebuilding from markers wipes the drag baseline, so restore it.
    if settings.drag_mode:
        from . import drag
        drag.sync_from_markers(scene)

    return problems


def _items_to_ranges(scene, settings, only_labels=None):
    """Turn UI items into core.RetimeRange objects.

    Built from each item's *baseline*, not from the live markers, so a marker
    nudged by hand cannot change what gets retimed.
    """
    result = []
    for item in settings.ranges:
        if only_labels is not None and item.label not in only_labels:
            continue
        if item.base_end <= item.base_start:
            continue
        retime = core.RetimeRange(item.label, item.base_start, item.base_end)
        retime.new_duration = item.new_duration
        retime.ripple = item.ripple
        retime.enabled = item.enabled
        result.append(retime)
    result.sort(key=lambda r: r.start)
    return result


def _apply_map(scene, frame_map, settings, objects=None):
    """Push one frame map through every animated datablock in scope."""
    stats = {"keys": 0, "actions": 0, "gp": 0, "markers": 0, "strips": 0}
    if frame_map.is_identity:
        return stats

    for action in core.collect_actions(scene, objects):
        stats["keys"] += core.remap_action(action, frame_map)
        stats["actions"] += 1

    if settings.include_gpencil:
        sources = scene.objects if objects is None else objects
        for obj in sources:
            if compat.is_grease_pencil(obj):
                stats["gp"] += core.remap_grease_pencil(obj, frame_map)

    if settings.include_nla:
        stats["strips"] += core.remap_nla_strips(
            core.collect_nla_strips(scene, objects), frame_map)

    # Markers are scene-wide, so they only move on the unfiltered pass.
    if objects is None and settings.include_markers:
        stats["markers"] += core.remap_markers(scene, frame_map)

    return stats


def _unique_label(settings, stem="range"):
    existing = {item.label for item in settings.ranges}
    if settings.pending_label:
        existing.add(settings.pending_label)
    index = 1
    while "%s%d" % (stem, index) in existing:
        index += 1
    return "%s%d" % (stem, index)


def _marker_names(prefix, label):
    """Names for a *new* pair. Use core.find_markers to look existing ones up."""
    return core.marker_names(prefix, label)


def suspicious_retimes(scene):
    """Ranges where both markers were dragged simultaneously.

    In drag mode, moving the start marker slides the range and moving the end
    marker retimes it. If both moved in the same session the user probably
    grabbed both markers to relocate the range, creating an unintended retime.
    Returns those labels so the UI can offer a commit path.
    """
    settings = scene.scene_retimer
    if not settings.drag_mode:
        return []
    flagged = []
    for item in settings.ranges:
        if item.start_was_dragged:
            flagged.append(item.label)
    return flagged


def _all_keyframe_frames(scene):
    """Every keyframe position in the scene, sorted, for snapping."""
    frames = set()
    for action in core.collect_actions(scene):
        for fcurve in compat.iter_fcurves(action):
            for key in fcurve.keyframe_points:
                frames.add(int(round(key.co.x)))
    return sorted(frames)


class SR_OT_sync(Operator):
    bl_idname = "scene_retimer.sync"
    bl_label = "Refresh Ranges"
    bl_description = "Rescan the timeline markers for tagged retime pairs"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        problems = sync_ranges(context.scene)
        for problem in problems:
            self.report({"WARNING"}, problem)
        return {"FINISHED"}


class SR_OT_add_pair(Operator):
    bl_idname = "scene_retimer.add_pair"
    bl_label = "Add Retime Range"
    bl_description = (
        "Create a tagged marker pair. Defaults to the preview range, or the "
        "current frame plus the given length"
    )
    bl_options = {"REGISTER", "UNDO"}

    label: StringProperty(name="Label", default="range")
    start: IntProperty(name="Start Frame")
    end: IntProperty(name="End Frame")

    def invoke(self, context, event):
        scene = context.scene
        if scene.use_preview_range:
            self.start = scene.frame_preview_start
            self.end = scene.frame_preview_end
        else:
            self.start = scene.frame_current
            self.end = scene.frame_current + 24
        # Suggest a label that is not taken yet.
        existing = {item.label for item in _settings(context).ranges}
        index = 1
        while "range%d" % index in existing:
            index += 1
        self.label = "range%d" % index
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        scene = context.scene
        settings = _settings(context)
        label = self.label.strip().replace(" ", "_")
        if not label:
            self.report({"ERROR"}, "Label cannot be empty")
            return {"CANCELLED"}

        start, end = sorted((self.start, self.end))
        if start == end:
            self.report({"ERROR"}, "Range must be at least one frame long")
            return {"CANCELLED"}

        if any(item.label == label for item in settings.ranges):
            self.report({"ERROR"}, "A range called '%s' already exists" % label)
            return {"CANCELLED"}

        prefix = settings.prefix
        scene.timeline_markers.new("%s%s_1" % (prefix, label), frame=start)
        scene.timeline_markers.new("%s%s_2" % (prefix, label), frame=end)

        sync_ranges(scene)
        for index, item in enumerate(settings.ranges):
            if item.label == label:
                settings.active_index = index
                break
        return {"FINISHED"}


class SR_OT_remove_pair(Operator):
    bl_idname = "scene_retimer.remove_pair"
    bl_label = "Remove Retime Range"
    bl_description = "Delete this range's marker pair from the timeline"
    bl_options = {"REGISTER", "UNDO"}

    label: StringProperty()

    def execute(self, context):
        scene = context.scene
        prefix = _settings(context).prefix
        for marker in core.find_markers(scene, prefix, self.label):
            if marker is not None:
                scene.timeline_markers.remove(marker)
        sync_ranges(scene)
        return {"FINISHED"}


class SR_OT_select_markers(Operator):
    bl_idname = "scene_retimer.select_markers"
    bl_label = "Jump To Range"
    bl_description = "Set the preview range and playhead to this retime range"
    bl_options = {"REGISTER", "UNDO"}

    label: StringProperty()

    def execute(self, context):
        scene = context.scene
        for item in _settings(context).ranges:
            if item.label != self.label:
                continue
            scene.use_preview_range = True
            scene.frame_preview_start = item.orig_start
            scene.frame_preview_end = item.orig_end
            scene.frame_current = item.orig_start
            return {"FINISHED"}
        return {"CANCELLED"}


class SR_OT_reset(Operator):
    bl_idname = "scene_retimer.reset"
    bl_label = "Reset Values"
    bl_description = "Set every range back to a 1.0 scale"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for item in _settings(context).ranges:
            item.new_duration = item.orig_duration
        return {"FINISHED"}


class SR_OT_initialize(Operator):
    """Two-click range building: drop the opening marker, scrub, close it."""

    bl_idname = "scene_retimer.initialize"
    bl_label = "Initialize Range"
    bl_description = (
        "Drop the opening marker at the current frame. Scrub to where the "
        "range should end, then press Set Range End to close it"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        settings = _settings(context)
        frame = scene.frame_current

        if not settings.pending_label:
            label = _unique_label(settings)
            start_name, _ = _marker_names(settings.prefix, label)
            scene.timeline_markers.new(start_name, frame=frame)
            settings.pending_label = label
            settings.pending_frame = frame
            self.report({"INFO"},
                        "Opened '%s' at frame %d -- scrub and close it"
                        % (label, frame))
            return {"FINISHED"}

        # Second click: close the range.
        label = settings.pending_label
        if frame == settings.pending_frame:
            self.report({"ERROR"},
                        "Move to a different frame before closing the range")
            return {"CANCELLED"}

        _, end_name = _marker_names(settings.prefix, label)
        scene.timeline_markers.new(end_name, frame=frame)
        settings.pending_label = ""

        sync_ranges(scene)
        for index, item in enumerate(settings.ranges):
            if item.label == label:
                settings.active_index = index
                break
        self.report({"INFO"}, "Closed '%s' (%d frames)"
                    % (label, abs(frame - settings.pending_frame)))
        return {"FINISHED"}


class SR_OT_cancel_pending(Operator):
    bl_idname = "scene_retimer.cancel_pending"
    bl_label = "Cancel"
    bl_description = "Discard the half-built range and remove its opening marker"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        settings = _settings(context)
        if not settings.pending_label:
            return {"CANCELLED"}
        start_name, _ = _marker_names(settings.prefix, settings.pending_label)
        for marker in [m for m in scene.timeline_markers if m.name == start_name]:
            scene.timeline_markers.remove(marker)
        settings.pending_label = ""
        return {"FINISHED"}


class SR_OT_rename(Operator):
    bl_idname = "scene_retimer.rename"
    bl_label = "Rename Range"
    bl_description = "Rename this range and both of its markers"
    bl_options = {"REGISTER", "UNDO"}

    new_label: StringProperty(name="New Label")

    def invoke(self, context, event):
        settings = _settings(context)
        if not len(settings.ranges):
            return {"CANCELLED"}
        self.new_label = settings.ranges[settings.active_index].label
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        scene = context.scene
        settings = _settings(context)
        if not len(settings.ranges):
            return {"CANCELLED"}

        item = settings.ranges[settings.active_index]
        old_label = item.label
        new_label = self.new_label.strip().replace(" ", "_")

        if not new_label:
            self.report({"ERROR"}, "Label cannot be empty")
            return {"CANCELLED"}
        if new_label == old_label:
            return {"CANCELLED"}
        if any(o.label == new_label for o in settings.ranges):
            self.report({"ERROR"}, "'%s' already exists" % new_label)
            return {"CANCELLED"}

        # Renaming also migrates a legacy _1/_2 pair to _start/_end.
        new_names = _marker_names(settings.prefix, new_label)
        for marker, new_name in zip(
                core.find_markers(scene, settings.prefix, old_label), new_names):
            if marker is not None:
                marker.name = new_name

        # Carry the dialled-in values across to the new label.
        keep = (item.new_duration, item.enabled, item.ripple, item.use_selection)
        sync_ranges(scene)
        for index, renamed in enumerate(settings.ranges):
            if renamed.label == new_label:
                (renamed.new_duration, renamed.enabled,
                 renamed.ripple, renamed.use_selection) = keep
                settings.active_index = index
                break
        return {"FINISHED"}


class SR_OT_set_flag(Operator):
    """Bulk-set one boolean across every range."""

    bl_idname = "scene_retimer.set_flag"
    bl_label = "Set Flag"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    flag: StringProperty()
    value: BoolProperty()

    def execute(self, context):
        for item in _settings(context).ranges:
            setattr(item, self.flag, self.value)
        return {"FINISHED"}


class SR_OT_commit_as_source(Operator):
    """Adopt the current marker positions as the range's source, discarding
    any pending retime."""

    bl_idname = "scene_retimer.commit_as_source"
    bl_label = "Commit To New Range"
    bl_description = (
        "Treat where the markers are RIGHT NOW as the new source range and "
        "reset the retime to 1.0. Use this in drag mode when you moved both "
        "markers to a different beat and want to start over from there, "
        "rather than have that move interpreted as a retime"
    )
    bl_options = {"REGISTER", "UNDO"}

    all_ranges: BoolProperty(name="All Ranges", default=False)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        scene = context.scene
        settings = _settings(context)
        if not len(settings.ranges):
            return {"CANCELLED"}

        if self.all_ranges:
            targets = list(settings.ranges)
        else:
            targets = [settings.ranges[settings.active_index]]

        committed = 0
        for item in targets:
            start, end = core.find_markers(scene, settings.prefix, item.label)
            if start is None or end is None:
                continue
            s, e = sorted((start.frame, end.frame))
            if s == e:
                continue
            item.base_start, item.base_end = s, e
            item.orig_start, item.orig_end = s, e
            item.orig_duration = max(1, e - s)
            item.new_duration = item.orig_duration
            item.scale = 1.0
            item.start_was_dragged = False
            committed += 1

        self.report({"INFO"}, "Committed %d range(s) as new source" % committed)
        return {"FINISHED"}


class SR_OT_select_marker(Operator):
    """Select and jump to one end of a range's marker pair."""

    bl_idname = "scene_retimer.select_marker"
    bl_label = "Select Marker"
    bl_description = (
        "Select this range's start or end marker and jump to it. Useful when "
        "two ranges' markers land on the same frame and are impossible to "
        "click apart in the timeline"
    )
    bl_options = {"REGISTER", "UNDO"}

    label: StringProperty()
    which: StringProperty()  # "start" or "end"

    def execute(self, context):
        scene = context.scene
        prefix = _settings(context).prefix
        start, end = core.find_markers(scene, prefix, self.label)
        wanted = start if self.which == "start" else end
        if wanted is None:
            self.report({"WARNING"}, "Marker not found")
            return {"CANCELLED"}

        for marker in scene.timeline_markers:
            marker.select = (marker == wanted)
        scene.frame_current = wanted.frame
        return {"FINISHED"}


class SR_OT_snap_markers(Operator):
    bl_idname = "scene_retimer.snap_markers"
    bl_label = "Snap Markers To Keyframes"
    bl_description = (
        "Move this range's markers onto the nearest existing keyframe, so the "
        "range lines up with the animation instead of landing between keys"
    )
    bl_options = {"REGISTER", "UNDO"}

    all_ranges: BoolProperty(name="All Ranges", default=False)

    def execute(self, context):
        scene = context.scene
        settings = _settings(context)
        if not len(settings.ranges):
            return {"CANCELLED"}

        keys = _all_keyframe_frames(scene)
        if not keys:
            self.report({"WARNING"}, "No keyframes in the scene to snap to")
            return {"CANCELLED"}

        if self.all_ranges:
            targets = list(settings.ranges)
        else:
            targets = [settings.ranges[settings.active_index]]

        moved = 0
        for item in targets:
            start, end = core.find_markers(scene, settings.prefix, item.label)
            for marker, anchor in ((start, item.orig_start), (end, item.orig_end)):
                if marker is None:
                    continue
                nearest = min(keys, key=lambda k: abs(k - anchor))
                if nearest != marker.frame:
                    marker.frame = nearest
                    moved += 1

        # Markers define the range, so the ordinary sync picks the move up.
        sync_ranges(scene)
        self.report({"INFO"}, "Snapped %d marker(s)" % moved)
        return {"FINISHED"}


class SR_OT_delete_all(Operator):
    bl_idname = "scene_retimer.delete_all"
    bl_label = "Delete All Ranges"
    bl_description = "Remove every tagged marker pair from the timeline"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        scene = context.scene
        settings = _settings(context)
        wanted = set()
        for item in settings.ranges:
            wanted.update(_marker_names(settings.prefix, item.label))
        for marker in [m for m in scene.timeline_markers if m.name in wanted]:
            scene.timeline_markers.remove(marker)
        settings.pending_label = ""
        sync_ranges(scene)
        return {"FINISHED"}


class SR_OT_preview_all(Operator):
    bl_idname = "scene_retimer.preview_all"
    bl_label = "Preview Range Covers All"
    bl_description = "Set the preview range to span every retime range"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        settings = _settings(context)
        if not len(settings.ranges):
            return {"CANCELLED"}
        scene.use_preview_range = True
        scene.frame_preview_start = min(i.orig_start for i in settings.ranges)
        scene.frame_preview_end = max(i.orig_end for i in settings.ranges)
        return {"FINISHED"}


class SR_OT_apply(Operator):
    bl_idname = "scene_retimer.apply"
    bl_label = "Apply Retime"
    bl_description = (
        "Retime the scene using the enabled ranges. This edits keyframes "
        "destructively -- undo works, but save first on a big scene"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = context.scene.scene_retimer
        return any(item.enabled and item.new_duration != item.orig_duration
                   for item in settings.ranges)

    def execute(self, context):
        scene = context.scene
        settings = _settings(context)

        # Pick up any marker moves first, then park the markers back onto the
        # resulting baseline. In drag mode the closing marker sits at the
        # *target* frame, and a marker left off its baseline would be remapped
        # from the wrong place and end up travelling twice.
        sync_ranges(scene)
        for item in settings.ranges:
            start, end = core.find_markers(scene, settings.prefix, item.label)
            if start is not None:
                start.frame = item.base_start
            if end is not None:
                end.frame = item.base_end

        _, problems = core.parse_ranges(scene, settings.prefix)
        if core.has_overlap(_items_to_ranges(scene, settings)):
            self.report({"ERROR"},
                        "Ranges overlap -- they cannot be retimed together")
            return {"CANCELLED"}

        selected_labels = {item.label for item in settings.ranges
                           if item.use_selection}
        selected_objects = list(context.selected_objects)
        if selected_labels and not selected_objects:
            self.report({"ERROR"},
                        "A range is set to Selected Only but nothing is selected")
            return {"CANCELLED"}

        original_end = scene.frame_end
        totals = {"keys": 0, "actions": 0, "gp": 0, "markers": 0, "strips": 0}

        # Pass 1: scene-wide ranges. Markers move here, which is what lets the
        # filtered pass below re-read its own (now shifted) boundaries.
        global_ranges = [r for r in _items_to_ranges(scene, settings)
                         if r.label not in selected_labels]
        global_map = core.FrameMap(global_ranges)
        for key, value in _apply_map(scene, global_map, settings).items():
            totals[key] += value

        # Pass 2: one map per selection-filtered range, applied to that
        # selection only. Kept separate so a filtered range never shifts the
        # objects it was explicitly excluded from.
        for label in sorted(selected_labels):
            filtered = _items_to_ranges(scene, settings, only_labels={label})
            filtered_map = core.FrameMap(filtered)
            for key, value in _apply_map(
                    scene, filtered_map, settings, selected_objects).items():
                totals[key] += value

        if settings.adjust_scene_range:
            new_end = int(round(global_map(original_end)))
            if new_end > scene.frame_end:
                scene.frame_end = new_end

        # The frame map has just moved the markers onto the new timing, so they
        # are authoritative again -- adopt them and reset every range to neutral.
        sync_ranges(scene, rebaseline=True)
        self.report(
            {"INFO"},
            "Retimed %d keys across %d actions (%d markers, %d GP frames, "
            "%d NLA strips)" % (totals["keys"], totals["actions"],
                                totals["markers"], totals["gp"],
                                totals["strips"]))
        return {"FINISHED"}


classes = (
    SR_OT_sync,
    SR_OT_add_pair,
    SR_OT_remove_pair,
    SR_OT_select_markers,
    SR_OT_reset,
    SR_OT_initialize,
    SR_OT_cancel_pending,
    SR_OT_rename,
    SR_OT_set_flag,
    SR_OT_commit_as_source,
    SR_OT_select_marker,
    SR_OT_snap_markers,
    SR_OT_delete_all,
    SR_OT_preview_all,
    SR_OT_apply,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
