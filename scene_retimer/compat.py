"""Version compatibility helpers for Blender 4.x and 5.x.

Blender 4.4 introduced slotted Actions; `Action.fcurves` was removed in 5.x in
favour of the layers -> strips -> channelbags hierarchy.  Everything that needs
to walk curves goes through `iter_fcurves` so the rest of the addon stays
version agnostic.
"""

import bpy


def iter_fcurves(action):
    """Yield every FCurve in an Action on both the legacy and slotted APIs."""
    if action is None:
        return

    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        # Blender 4.x, and 5.x actions that still expose a legacy view.
        for fcurve in legacy:
            yield fcurve
        return

    for layer in action.layers:
        for strip in layer.strips:
            # Only keyframe strips carry channelbags.
            channelbags = getattr(strip, "channelbags", None)
            if channelbags is None:
                continue
            for channelbag in channelbags:
                for fcurve in channelbag.fcurves:
                    yield fcurve


def gp_layers(gp_data):
    """Yield Grease Pencil layers for both the GPv2 and GPv3 data blocks."""
    layers = getattr(gp_data, "layers", None)
    if layers is None:
        return
    for layer in layers:
        yield layer


def is_grease_pencil(obj):
    return obj.type in {"GPENCIL", "GREASEPENCIL"}
