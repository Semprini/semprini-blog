"""Render the cut plane region (z < zmax) from below with a 0.1 grid; print radial outlines.
Usage: blender -b file --factory-startup --python render_cut.py -- outdir zmax
"""
import bpy, bmesh, sys, os, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
outdir, zmax = argv[0], float(argv[1])
os.makedirs(outdir, exist_ok=True)
scene = bpy.context.scene

ob = bpy.data.objects['mesh']
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True); bpy.context.view_layer.objects.active = ob
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

bm = bmesh.new(); bm.from_mesh(ob.data)
# delete everything above zmax
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z > zmax], context='VERTS')
bm.to_mesh(ob.data); bm.free()

# grid lines in the z=-1.05 plane
for i in range(-9, 10):
    c = i * 0.1
    bpy.ops.mesh.primitive_cylinder_add(radius=0.003, depth=2.2, location=(c, -0.2, -1.05), rotation=(1.5708, 0, 0))
    bpy.ops.mesh.primitive_cylinder_add(radius=0.003, depth=2.2, location=(0, c, -1.05), rotation=(0, 1.5708, 0))
    if i % 5 == 0:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.008, depth=2.2, location=(c, -0.2, -1.05), rotation=(1.5708, 0, 0))
        bpy.ops.mesh.primitive_cylinder_add(radius=0.008, depth=2.2, location=(0, c, -1.05), rotation=(0, 1.5708, 0))

scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'STUDIO'
scene.display.shading.color_type = 'TEXTURE'
scene.render.resolution_x = scene.render.resolution_y = 900
cam_data = bpy.data.cameras.new("C"); cam_data.type = 'ORTHO'; cam_data.ortho_scale = 2.0
cam = bpy.data.objects.new("C", cam_data); scene.collection.objects.link(cam); scene.camera = cam
cam.location = (0, -0.2, -6)
# look up +z, with -y (front) at bottom of image, +x at LEFT of image (mirror, since viewed from below)
cam.rotation_euler = Vector((0, 0, 1)).to_track_quat('-Z', 'Y').to_euler()
scene.render.filepath = os.path.join(outdir, "cut_bottom.png")
bpy.ops.render.render(write_still=True); print("WROTE", scene.render.filepath)
cam.location = (0, -0.2, 6)
cam.rotation_euler = Vector((0, 0, -1)).to_track_quat('-Z', 'Y').to_euler()
scene.render.filepath = os.path.join(outdir, "cut_top.png")
bpy.ops.render.render(write_still=True); print("WROTE", scene.render.filepath)
