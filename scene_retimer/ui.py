"""Panels. Shown in the Dope Sheet, Graph Editor and 3D View sidebars."""

import bpy
from bpy.types import Menu, Panel, UIList

from . import core


class SR_UL_ranges(UIList):
    """One row per retime range: enable, name, bounds, and the frame delta."""

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_prop, index):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.prop(item, "enabled", text="")

            name = row.row(align=True)
            name.active = item.enabled
            name.label(text=item.label, icon="MARKER_HLT")
            name.label(text="%d-%d" % (item.orig_start, item.orig_end))

            delta = item.new_duration - item.orig_duration
            info = row.row(align=True)
            info.active = item.enabled
            info.alignment = "RIGHT"
            if delta:
                info.label(text="%+d" % delta)
                if not item.ripple:
                    info.label(text="", icon="SNAP_MIDPOINT")
                if item.use_selection:
                    info.label(text="", icon="RESTRICT_SELECT_OFF")
            else:
                info.label(text="--")
        else:
            layout.label(text=item.label)


class SR_MT_specials(Menu):
    bl_idname = "SR_MT_specials"
    bl_label = "Retime Range Specials"

    def draw(self, context):
        layout = self.layout

        layout.operator("scene_retimer.rename", icon="OUTLINER_DATA_FONT")
        layout.operator("scene_retimer.snap_markers",
                        text="Snap Markers To Keyframes",
                        icon="SNAP_ON").all_ranges = False
        layout.operator("scene_retimer.snap_markers",
                        text="Snap All To Keyframes",
                        icon="SNAP_ON").all_ranges = True

        layout.separator()

        enable = layout.operator("scene_retimer.set_flag",
                                 text="Enable All", icon="CHECKBOX_HLT")
        enable.flag, enable.value = "enabled", True
        disable = layout.operator("scene_retimer.set_flag",
                                  text="Disable All", icon="CHECKBOX_DEHLT")
        disable.flag, disable.value = "enabled", False

        layout.separator()

        ripple_on = layout.operator("scene_retimer.set_flag",
                                    text="Ripple All On", icon="FORWARD")
        ripple_on.flag, ripple_on.value = "ripple", True
        ripple_off = layout.operator("scene_retimer.set_flag",
                                     text="Ripple All Off", icon="SNAP_MIDPOINT")
        ripple_off.flag, ripple_off.value = "ripple", False

        layout.separator()

        expand = layout.operator("scene_retimer.set_flag",
                                 text="Selected Only: All On",
                                 icon="RESTRICT_SELECT_OFF")
        expand.flag, expand.value = "use_selection", True
        collapse = layout.operator("scene_retimer.set_flag",
                                   text="Selected Only: All Off",
                                   icon="RESTRICT_SELECT_ON")
        collapse.flag, collapse.value = "use_selection", False

        layout.separator()

        layout.operator("scene_retimer.preview_all", icon="PREVIEW_RANGE")
        layout.operator("scene_retimer.reset", text="Reset All Values",
                        icon="LOOP_BACK")

        layout.separator()

        commit_active = layout.operator(
            "scene_retimer.commit_as_source",
            text="Commit Active To New Range", icon="CHECKMARK")
        commit_active.all_ranges = False
        commit_all = layout.operator(
            "scene_retimer.commit_as_source",
            text="Commit All To New Range", icon="CHECKMARK")
        commit_all.all_ranges = True

        layout.separator()

        layout.operator("scene_retimer.delete_all", icon="TRASH")


def _draw_builder(layout, context):
    """The two-click range builder, plus the dialog-based fallback."""
    settings = context.scene.scene_retimer
    frame = context.scene.frame_current

    if settings.pending_label:
        box = layout.box()
        header = box.row(align=True)
        header.label(text="Building '%s'" % settings.pending_label,
                     icon="REC")
        header.operator("scene_retimer.cancel_pending", text="", icon="X")

        length = abs(frame - settings.pending_frame)
        box.label(text="Opened at %d, now at %d (%d frames)"
                       % (settings.pending_frame, frame, length))

        close = box.row()
        close.scale_y = 1.3
        close.enabled = frame != settings.pending_frame
        close.operator("scene_retimer.initialize",
                       text="Set Range End", icon="CHECKMARK")
        if frame == settings.pending_frame:
            box.label(text="Scrub to another frame first", icon="INFO")
        return

    row = layout.row(align=True)
    row.scale_y = 1.3
    row.operator("scene_retimer.initialize",
                 text="Initialize Range At %d" % frame, icon="REC")


def _draw_active(layout, context):
    settings = context.scene.scene_retimer
    if not len(settings.ranges):
        return
    index = min(settings.active_index, len(settings.ranges) - 1)
    item = settings.ranges[index]

    box = layout.box()
    box.active = item.enabled

    header = box.row(align=True)
    header.label(text=item.label, icon="MARKER_HLT")

    # Select just the start or end marker -- essential when two ranges' markers
    # share a frame and are impossible to click apart in the timeline.
    pick_start = header.operator("scene_retimer.select_marker",
                                 text="", icon="TRIA_LEFT_BAR")
    pick_start.label, pick_start.which = item.label, "start"
    pick_end = header.operator("scene_retimer.select_marker",
                               text="", icon="TRIA_RIGHT_BAR")
    pick_end.label, pick_end.which = item.label, "end"

    jump = header.operator("scene_retimer.select_markers", text="",
                           icon="PREVIEW_RANGE")
    jump.label = item.label

    # Live marker sliders: drag either end to move the actual timeline marker.
    handles = box.row(align=True)
    handles.prop(item, "handle_start", text="Start")
    handles.prop(item, "handle_end", text="End")
    box.label(text="%d frames long" % item.orig_duration)

    # Linked pair: editing either field updates the other.
    fields = box.row(align=True)
    fields.prop(item, "new_duration", text="Frames")
    fields.prop(item, "scale", text="Scale")

    toggles = box.row(align=True)
    toggles.prop(item, "ripple", toggle=True,
                 icon="FORWARD" if item.ripple else "SNAP_MIDPOINT")
    toggles.prop(item, "use_selection", toggle=True,
                 icon="RESTRICT_SELECT_OFF")


def _draw_body(layout, context):
    scene = context.scene
    settings = scene.scene_retimer

    header = layout.row(align=True)
    header.prop(settings, "prefix", text="Tag")
    header.operator("scene_retimer.sync", text="", icon="FILE_REFRESH")

    _draw_builder(layout, context)

    _, problems = core.parse_ranges(scene, settings.prefix)
    # A half-built range is always "missing marker _2" -- that is the workflow,
    # not a mistake, so hide that one warning while it is in progress.
    if settings.pending_label:
        problems = [p for p in problems
                    if settings.pending_label not in p]
    if problems:
        box = layout.box()
        box.label(text="Marker problems:", icon="ERROR")
        for problem in problems[:4]:
            box.label(text=problem)

    if not len(settings.ranges):
        info = layout.box()
        info.label(text="No retime ranges yet.", icon="INFO")
        info.label(text="Use Initialize Range above, or")
        info.label(text="name markers %sname_start / %sname_end"
                        % (settings.prefix, settings.prefix))
        return

    drag_row = layout.row(align=True)
    drag_row.scale_y = 1.2
    drag_row.prop(settings, "drag_mode", toggle=True,
                  icon="ARROW_LEFTRIGHT" if settings.drag_mode else "MARKER")
    if settings.drag_mode:
        from . import ops as sr_ops
        suspicious = sr_ops.suspicious_retimes(scene)

        if suspicious:
            hint = layout.box()
            hint.alert = True
            hint.label(text="Both markers moved on: %s"
                            % ", ".join(suspicious[:3]), icon="ERROR")
            hint.label(text="If you meant to relocate the range,")
            hint.label(text="commit the markers as the new source:")
            commit = hint.operator("scene_retimer.commit_as_source",
                                   text="Commit To New Range",
                                   icon="CHECKMARK")
            commit.all_ranges = False

    listing = layout.row()
    listing.template_list("SR_UL_ranges", "", settings, "ranges",
                          settings, "active_index", rows=4)

    side = listing.column(align=True)
    side.operator("scene_retimer.add_pair", text="", icon="ADD")
    remove = side.operator("scene_retimer.remove_pair", text="", icon="REMOVE")
    remove.label = settings.ranges[
        min(settings.active_index, len(settings.ranges) - 1)].label
    side.separator()
    side.menu("SR_MT_specials", icon="DOWNARROW_HLT", text="")

    _draw_active(layout, context)

    total_delta = sum(item.new_duration - item.orig_duration
                      for item in settings.ranges
                      if item.enabled and item.ripple)
    if total_delta:
        layout.label(text="Scene length change: %+d frames" % total_delta,
                     icon="TIME")

    options = layout.box()
    options.label(text="Affect:")
    grid = options.grid_flow(columns=2, even_columns=True, align=True)
    grid.prop(settings, "include_markers")
    grid.prop(settings, "include_nla")
    grid.prop(settings, "include_gpencil")
    grid.prop(settings, "adjust_scene_range")

    apply_row = layout.row()
    apply_row.scale_y = 1.4
    apply_row.operator("scene_retimer.apply", icon="MOD_TIME")


class SR_PT_base:
    bl_label = "Scene Retimer"
    bl_space_type = "DOPESHEET_EDITOR"
    bl_region_type = "UI"
    bl_category = "Retime"

    def draw(self, context):
        _draw_body(self.layout, context)


class SR_PT_dopesheet(SR_PT_base, Panel):
    bl_idname = "SR_PT_dopesheet"


class SR_PT_view3d(SR_PT_base, Panel):
    bl_idname = "SR_PT_view3d"
    bl_space_type = "VIEW_3D"


class SR_PT_graph(SR_PT_base, Panel):
    bl_idname = "SR_PT_graph"
    bl_space_type = "GRAPH_EDITOR"


classes = (
    SR_UL_ranges,
    SR_MT_specials,
    SR_PT_dopesheet,
    SR_PT_view3d,
    SR_PT_graph,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
