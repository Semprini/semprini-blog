"""Render orthographic-ish views of the avatar for inspection.
Usage: blender -b file.blend --factory-startup --python render_views.py -- <outdir> [object_name]
"""
import bpy, sys, math, os
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
outdir = argv[0] if argv else "/tmp/semprini_views"
obname = argv[1] if len(argv) > 1 else None
os.makedirs(outdir, exist_ok=True)

scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'STUDIO'
scene.display.shading.color_type = 'TEXTURE'
scene.display.shading.show_xray = False
scene.render.resolution_x = 600
scene.render.resolution_y = 600
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
scene.world = scene.world or bpy.data.worlds.new("W")
scene.world.color = (0.2, 0.2, 0.2)

meshes = [o for o in scene.objects if o.type == 'MESH' and (obname is None or o.name == obname)]
# compute world bbox of all meshes
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center = (mn + mx) / 2
size = max(mx - mn) * 1.15

cam_data = bpy.data.cameras.new("InspectCam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = size
cam_data.clip_end = 100
cam = bpy.data.objects.new("InspectCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

# also show armature bones in front if present
for o in scene.objects:
    if o.type == 'ARMATURE':
        o.show_in_front = True
        o.data.display_type = 'OCTAHEDRAL'

views = {
    "front": (0, -1, 0),
    "back": (0, 1, 0),
    "left": (-1, 0, 0),
    "right": (1, 0, 0),
    "top": (0, 0, 1),
    "bottom": (0, 0, -1),
    "front_q": (-0.7, -0.7, 0.3),
}
for name, d in views.items():
    d = Vector(d).normalized()
    cam.location = center + d * 10
    up = Vector((0, 0, 1)) if abs(d.z) < 0.99 else Vector((0, 1, 0))
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = os.path.join(outdir, f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("WROTE", scene.render.filepath)
