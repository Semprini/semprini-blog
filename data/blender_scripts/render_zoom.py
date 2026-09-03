"""Zoomed ortho renders of a z-range, with horizontal reference lines every 0.1.
Usage: blender -b file --factory-startup --python render_zoom.py -- outdir zmin zmax
"""
import bpy, sys, os
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
outdir, zmin, zmax = argv[0], float(argv[1]), float(argv[2])
os.makedirs(outdir, exist_ok=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'STUDIO'
scene.display.shading.color_type = 'TEXTURE'
scene.render.resolution_x = scene.render.resolution_y = 800
scene.render.resolution_percentage = 100

# reference lines: thin cylinders along X at each 0.1 z
for i in range(int(round((zmax - zmin) / 0.1)) + 1):
    z = zmin + i * 0.1
    bpy.ops.mesh.primitive_cylinder_add(radius=0.004, depth=3, location=(0, -1.2, z), rotation=(0, 1.5708, 0))
    bpy.ops.mesh.primitive_cylinder_add(radius=0.004, depth=3, location=(1.2, 0, z), rotation=(1.5708, 0, 0))

cam_data = bpy.data.cameras.new("C"); cam_data.type = 'ORTHO'
cam_data.ortho_scale = (zmax - zmin) * 1.1 * 800 / 800
cam = bpy.data.objects.new("C", cam_data); scene.collection.objects.link(cam); scene.camera = cam
center = Vector((0, -0.2, (zmin + zmax) / 2))
for name, d in {"front": (0, -1, 0), "left": (-1, 0, 0), "right": (1, 0, 0)}.items():
    d = Vector(d)
    cam.location = center + d * 10
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = os.path.join(outdir, f"zoom_{name}.png")
    bpy.ops.render.render(write_still=True)
    print("WROTE", scene.render.filepath)
