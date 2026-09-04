"""Confirm mouth/nose shells: tint candidates over texture and render the muzzle.
Usage: blender -b data/Semprini.blend --factory-startup --python confirm_mouth.py -- <outdir>
"""
import sys, os
import bpy, bmesh
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
outdir = argv[0] if argv else "/tmp/mouth"
os.makedirs(outdir, exist_ok=True)

ob = bpy.data.objects["mesh"]
bpy.ops.object.select_all(action="DESELECT")
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = ob.data

bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()

seen = set()
comps = []
for v in bm.verts:
    if v.index in seen:
        continue
    stack = [v]
    comp = []
    while stack:
        cur = stack.pop()
        if cur.index in seen:
            continue
        seen.add(cur.index)
        comp.append(cur)
        for e in cur.link_edges:
            o = e.other_vert(cur)
            if o.index not in seen:
                stack.append(o)
    comps.append(comp)

# candidates keyed by centroid, matched from classify_shells output
targets = {
    "nose_big": ((-0.200, -0.508, -0.577), (0, 0, 1)),        # blue
    "muzzleA": ((-0.177, -0.925, -0.196), (0, 1, 0)),         # green
    "muzzleB": ((-0.132, -0.868, -0.104), (1, 1, 0)),         # yellow
    "muzzleC": ((-0.118, -0.850, -0.298), (1, 0, 0)),         # red
    "muzzleD": ((0.067, -0.862, -0.213), (1, 0.5, 0)),        # orange
    "below_nose": ((-0.213, -0.672, -0.558), (1, 0, 1)),      # magenta
}
comp_of = {}
for name, (c, col) in targets.items():
    c = Vector(c)
    best = min(range(len(comps)),
               key=lambda i: (sum((v.co for v in comps[i]), Vector()) / len(comps[i]) - c).length)
    comp_of[name] = best
    cc = sum((v.co for v in comps[best]), Vector()) / len(comps[best])
    print(f"{name}: comp{best} n={len(comps[best])} centre=({cc.x:.3f},{cc.y:.3f},{cc.z:.3f})")

for name, (c, col) in targets.items():
    m = bpy.data.materials.new("t_" + name)
    m.use_nodes = True
    m.diffuse_color = (*col, 1)
    me.materials.append(m)
    mi = len(me.materials) - 1
    idxs = {v.index for v in comps[comp_of[name]]}
    for f in bm.faces:
        if f.verts[0].index in idxs:
            f.material_index = mi
bm.to_mesh(me)
bm.free()

scene = bpy.context.scene
for o in list(scene.objects):
    if o.type in {"CAMERA", "LIGHT"}:
        bpy.data.objects.remove(o, do_unlink=True)
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.render.resolution_x = scene.render.resolution_y = 900
cam_data = bpy.data.cameras.new("C")
cam_data.type = "ORTHO"
cam = bpy.data.objects.new("C", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
for name, (target, d, s) in {
    "muzzle_front": (Vector((-0.1, -0.6, -0.35)), Vector((0, -1, 0)), 1.1),
    "muzzle_below": (Vector((-0.1, -0.6, -0.4)), Vector((0, -0.7, -1)), 1.1),
    "muzzle_side": (Vector((-0.1, -0.6, -0.35)), Vector((-1, -0.4, 0)), 1.1),
}.items():
    d = d.normalized()
    cam.location = target + d * 8
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam_data.ortho_scale = s
    scene.render.filepath = os.path.join(outdir, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("WROTE", scene.render.filepath)
