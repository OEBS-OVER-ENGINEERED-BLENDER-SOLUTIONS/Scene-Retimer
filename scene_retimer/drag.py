"""Drag-to-retime: turn the closing marker into a live scrub handle.

While drag mode is armed each range freezes a *baseline* (`base_start` /
`base_end`) taken from where its markers were when you armed it.  A timer then
watches the real marker positions and reads the gap between them as the new
duration.  Nothing is written to keyframes until you hit Apply -- dragging only
moves the target, so it stays undoable and non-destructive.

Two gestures, distinguished by which marker moved:

* drag the **closing** marker -> changes the duration (the retime itself)
* drag the **opening** marker -> slides the whole range, duration preserved
"""

import bpy

from . import core

_TIMER_INTERVAL = 0.1
_running = False


def arm(scene):
    """Freeze the current marker positions as each range's baseline."""
    settings = scene.scene_retimer
    for item in settings.ranges:
        item.base_start = item.orig_start
        item.base_end = item.orig_end
        item.start_was_dragged = False
    _start_timer()


def disarm(scene):
    _stop_timer()


def _start_timer():
    global _running
    if _running:
        return
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=_TIMER_INTERVAL)
    _running = True


def _stop_timer():
    global _running
    _running = False
    if bpy.app.timers.is_registered(_poll):
        try:
            bpy.app.timers.unregister(_poll)
        except ValueError:
            pass


def _tag_redraw():
    window_manager = bpy.data.window_managers[0] if bpy.data.window_managers else None
    if window_manager is None:
        return
    for window in window_manager.windows:
        for area in window.screen.areas:
            if area.type in {"DOPESHEET_EDITOR", "GRAPH_EDITOR", "VIEW_3D",
                             "TIMELINE"}:
                area.tag_redraw()


def sync_from_markers(scene):
    """Read marker positions and update the ranges. Returns True if anything moved."""
    settings = scene.scene_retimer
    prefix = settings.prefix
    changed = False

    for item in settings.ranges:
        start_marker, end_marker = core.find_markers(scene, prefix, item.label)
        if start_marker is None or end_marker is None:
            continue
        start_frame, end_frame = start_marker.frame, end_marker.frame

        # Opening marker moved -> slide the whole range, keep its duration.
        if start_frame != item.base_start:
            shift = start_frame - item.base_start
            item.base_start = start_frame
            item.base_end += shift
            item.start_was_dragged = True
            changed = True

        if item.orig_start != item.base_start or item.orig_end != item.base_end:
            item.orig_start = item.base_start
            item.orig_end = item.base_end
            # orig_duration must land before new_duration so the linked Scale
            # field derives from the right baseline.
            item.orig_duration = max(1, item.base_end - item.base_start)
            changed = True

        # Closing marker position is the target duration.
        target = max(1, end_frame - item.base_start)
        if item.new_duration != target:
            item.new_duration = target
            changed = True

    return changed


def _poll():
    """Timer callback. Cheap: only reads marker frames."""
    if not _running:
        return None

    try:
        for scene in bpy.data.scenes:
            settings = getattr(scene, "scene_retimer", None)
            if settings is None or not settings.drag_mode:
                continue
            if sync_from_markers(scene):
                _tag_redraw()
    except (AttributeError, ReferenceError):
        # Mid file-load the RNA can be torn down; skip this tick.
        pass

    return _TIMER_INTERVAL


def commit(scene):
    """After an Apply, re-baseline so the markers become handles again."""
    settings = scene.scene_retimer
    for item in settings.ranges:
        item.base_start = item.orig_start
        item.base_end = item.orig_end


@bpy.app.handlers.persistent
def _on_load(_dummy):
    # Drag mode is stored in the .blend, so restart the timer if it was on.
    for scene in bpy.data.scenes:
        settings = getattr(scene, "scene_retimer", None)
        if settings is not None and settings.drag_mode:
            _start_timer()
            return


def register():
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def unregister():
    _stop_timer()
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
