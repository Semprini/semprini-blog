"""Pose face bones (blink, wink, ears, brows, mouth) and render to validate the rig.
Usage: blender -b Semprini_rigged.blend --factory-startup --python face_pose_test.py -- outdir
"""
import sys, os, math
import bpy
from mathutils import Vector, Quaternion

argv = sys.argv[sys.argv.index("--") + 1:]
outdir = argv[0]
os.makedirs(outdir, exist_ok=True)
scene = bpy.context.scene
rig = bpy.data.objects["SempriniRig"]
bpy.ops.object.select_all(action="DESELECT")
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="POSE")
pb = rig.pose.bones

scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x = scene.render.resolution_y = 800
cam_data = bpy.data.cameras.new("C")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 1.9
cam = bpy.data.objects.new("C", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
d = Vector((0, -1, 0))
cam.location = Vector((0, -0.1, 0.15)) + d * 8
cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()

def shot(name):
    bpy.context.view_layer.update()
    scene.render.filepath = os.path.join(outdir, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("WROTE", scene.render.filepath)

def reset():
    for b in pb:
        b.location = (0, 0, 0)
        b.rotation_quaternion = (1, 0, 0, 0)
        b.rotation_euler = (0, 0, 0)
        b.scale = (1, 1, 1)
    lids()
    mouth()

# rest: lids retracted, mouth interior retracted (as JS will hold them)
def lids(l=0.06, r=0.06):
    pb["Lid.L"].scale.y = l
    pb["Lid.R"].scale.y = r

def mouth(open_=0.05, wide=0.4):
    pb["Mouth"].scale = (wide, open_, 1.0)

reset()
shot("01_rest_lids_open")

reset(); lids(1.0, 1.0)
shot("02_blink")

reset(); lids(0.06, 1.0)
shot("03_wink_R")

reset(); lids(0.45, 0.45)
pb["Brow.L"].location.y = -0.04
pb["Brow.R"].location.y = -0.04
shot("04_narrow_brows")

reset()
pb["Brow.L"].location.y = 0.05
pb["Brow.R"].location.y = 0.05
shot("05_brows_test")

# ears: rotate about pose-local axes to find the right ones
reset()
pb["Ear.R"].rotation_mode = "XYZ"
pb["Ear.R"].rotation_euler = (math.radians(25), 0, 0)
shot("06_earR_rotX25")

reset()
pb["Ear.R"].rotation_mode = "XYZ"
pb["Ear.R"].rotation_euler = (0, 0, math.radians(25))
shot("07_earR_rotZ25")

reset()
pb["Ear.L"].rotation_mode = "XYZ"
pb["Ear.L"].rotation_euler = (0, 0, math.radians(-60))
shot("08_earL_rotZ-60")

reset()
pb["Ear.L"].rotation_mode = "XYZ"
pb["Ear.L"].rotation_euler = (math.radians(-50), 0, 0)
shot("09_earL_rotX-50")

# mouth
reset()
mouth(1.0, 1.0)
shot("10_mouth_open")

reset()
mouth(0.5, 1.3)
shot("11_mouth_wide")
