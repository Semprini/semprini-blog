"""Classify head-region shells: print centroid/bbox/colour per component and render
them tinted with index labels baked into per-shell material colours.
Usage: blender -b data/Semprini.blend --factory-startup --python classify_shells.py -- <outdir>
"""
import sys, os, colorsys
import bpy, bmesh
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
outdir = argv[0] if argv else "/tmp/shells"
os.makedirs(outdir, exist_ok=True)

ob = bpy.data.objects["mesh"]
bpy.ops.object.select_all(action="DESELECT")
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = ob.data

img = next(n for n in me.materials[0].node_tree.nodes if n.type == "TEX_IMAGE").image
W, H = img.size
PIX = img.pixels[:]

def tex(uv):
    x = int(uv.x * W) % W
    y = int(uv.y * H) % H
    i = (y * W + x) * 4
    return (PIX[i], PIX[i + 1], PIX[i + 2])

bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()
uvl = bm.loops.layers.uv.active

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

# head region shells only (centroid z > -0.65), sorted by size
info = []
for ci, comp in enumerate(comps):
    c = sum((v.co for v in comp), Vector()) / len(comp)
    if c.z < -0.62:
        continue
    mn = Vector((min(v.co.x for v in comp), min(v.co.y for v in comp), min(v.co.z for v in comp)))
    mx = Vector((max(v.co.x for v in comp), max(v.co.y for v in comp), max(v.co.z for v in comp)))
    cols = []
    idxs = {v.index for v in comp}
    for f in bm.faces:
        for l in f.loops:
            if l.vert.index in idxs:
                cols.append(tex(l[uvl].uv))
                break
    mc = tuple(sum(col[i] for col in cols) / len(cols) for i in range(3)) if cols else (0, 0, 0)
    info.append((ci, comp, c, mn, mx, mc))

info.sort(key=lambda t: -len(t[1]))
print(f"head shells: {len(info)}")
for rank, (ci, comp, c, mn, mx, mc) in enumerate(info):
    print(f"shell{rank} (comp{ci}): n={len(comp)} centre=({c.x:.3f},{c.y:.3f},{c.z:.3f}) "
          f"x[{mn.x:.2f},{mx.x:.2f}] y[{mn.y:.2f},{mx.y:.2f}] z[{mn.z:.2f},{mx.z:.2f}] "
          f"col=({mc[0]:.2f},{mc[1]:.2f},{mc[2]:.2f})")

# tint: distinct hue per shell rank
mats = []
for rank in range(len(info)):
    m = bpy.data.materials.new(f"tint{rank}")
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    r, g, b = colorsys.hsv_to_rgb((rank * 0.61803) % 1.0, 0.95, 1.0)
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1)
    m.diffuse_color = (r, g, b, 1)   # workbench MATERIAL mode reads this
    me.materials.append(m)
    mats.append(len(me.materials) - 1)
    print(f"tint{rank}: rgb=({int(r*255)},{int(g*255)},{int(b*255)})")

vert2rank = {}
for rank, (ci, comp, *_rest) in enumerate(info):
    for v in comp:
        vert2rank[v.index] = rank
for f in bm.faces:
    r = vert2rank.get(f.verts[0].index)
    if r is not None:
        f.material_index = mats[r]
bm.to_mesh(me)
bm.free()

scene = bpy.context.scene
for o in list(scene.objects):
    if o.type in {"CAMERA", "LIGHT"}:
        bpy.data.objects.remove(o, do_unlink=True)
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.render.resolution_x = scene.render.resolution_y = 1000
cam_data = bpy.data.cameras.new("C")
cam_data.type = "ORTHO"
cam = bpy.data.objects.new("C", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
views = {
    "front": (Vector((0, -0.1, 0.2)), Vector((0, -1, 0)), 2.0),
    "left": (Vector((0.2, 0, 0.2)), Vector((1, 0, 0)), 2.0),
    "right": (Vector((-0.2, 0, 0.2)), Vector((-1, 0, 0)), 2.0),
    "top": (Vector((0, 0, 0.6)), Vector((0, 0, 1)), 1.8),
    "eyeR": (Vector((-0.27, -0.31, 0.45)), Vector((-0.15, -1, 0.1)), 0.45),
    "eyeL": (Vector((0.13, -0.31, 0.33)), Vector((0.15, -1, 0.1)), 0.45),
    "mouth": (Vector((-0.15, -0.9, -0.2)), Vector((0, -1, -0.25)), 0.7),
    "earR_up": (Vector((-0.5, -0.1, 0.75)), Vector((-0.6, -1, 0.3)), 0.8),
    "earL_fold": (Vector((0.6, -0.05, 0.35)), Vector((1, -0.5, 0.15)), 0.9),
}
for name, (target, d, s) in views.items():
    d = d.normalized()
    cam.location = target + d * 8
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam_data.ortho_scale = s
    scene.render.filepath = os.path.join(outdir, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("WROTE", scene.render.filepath)
