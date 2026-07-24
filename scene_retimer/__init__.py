bl_info = {
    "name": "Scene Retimer",
    "author": "OEBS Studios",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "Dope Sheet / Graph Editor / 3D View > Sidebar > Retime",
    "description": "Retime whole-scene animation using tagged marker pairs",
    "category": "Animation",
}

from . import props, drag, ops, ui

_modules = (props, drag, ops, ui)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()


if __name__ == "__main__":
    register()
