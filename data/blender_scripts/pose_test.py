"""Pose the rig (IK hand targets + look target) and render, to validate weights/IK.
Usage: blender -b Semprini_rigged.blend --factory-startup --python pose_test.py -- outdir
"""
import bpy, sys, os, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
outdir = argv[0]
os.makedirs(outdir, exist_ok=True)
scene = bpy.context.scene
rig = bpy.data.objects["SempriniRig"]
bpy.ops.object.select_all(action="DESELECT")
rig.select_set(True); bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="POSE")
pb = rig.pose.bones

def world_to_pose_loc(bone, world):
    # location offset in the bone's rest space so its head ends up at 'world'
    rest_head = rig.matrix_world @ bone.bone.head_local
    delta = world - rest_head
    return bone.bone.matrix_local.to_3x3().inverted() @ delta

# Pose A: point left paw forward, right arm slightly raised, look right/up
pb["IK_Hand.L"].location = world_to_pose_loc(pb["IK_Hand.L"], Vector((0.55, -0.95, -0.85)))
pb["IK_Hand.R"].location = world_to_pose_loc(pb["IK_Hand.R"], Vector((-0.75, -0.55, -1.15)))
pb["LookTarget"].location = world_to_pose_loc(pb["LookTarget"], Vector((-1.2, -1.4, 0.3)))
bpy.context.view_layer.update()

for b in ("UpperArm.L", "ForeArm.L", "Hand.L", "Head"):
    m = rig.matrix_world @ pb[b].matrix
    print(f"posed {b}: head={tuple(round(v,3) for v in m.translation)}")

bpy.ops.object.mode_set(mode="OBJECT")
rig.show_in_front = True
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'STUDIO'
scene.display.shading.color_type = 'TEXTURE'
scene.render.resolution_x = scene.render.resolution_y = 700
cam_data = bpy.data.cameras.new("C"); cam_data.type = 'ORTHO'; cam_data.ortho_scale = 3.0
cam = bpy.data.objects.new("C", cam_data); scene.collection.objects.link(cam); scene.camera = cam
center = Vector((0, -0.3, -0.2))
for name, d in {"front": (0, -1, 0), "quarter": (0.7, -0.7, 0.25), "side": (1, 0, 0)}.items():
    d = Vector(d).normalized()
    cam.location = center + d * 10
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = os.path.join(outdir, f"pose_{name}.png")
    bpy.ops.render.render(write_still=True)
    print("WROTE", scene.render.filepath)
