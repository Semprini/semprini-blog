"""Analyse the head: find eyes, mouth (dark texture patches on the front) and ears
(top extremities), and dump cluster stats. Also renders a face close-up with markers.
Usage: blender -b data/Semprini.blend --factory-startup --python analyze_face.py -- <outdir>
"""
import sys, os, math
import bpy, bmesh
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
outdir = argv[0] if argv else "/tmp/face"
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
uvl = bm.loops.layers.uv.active

# per-vertex mean colour
vcol = {}
for f in bm.faces:
    for l in f.loops:
        c = tex(l[uvl].uv)
        vcol.setdefault(l.vert.index, []).append(c)
for k, cs in vcol.items():
    n = len(cs)
    vcol[k] = tuple(sum(c[i] for c in cs) / n for i in range(3))

# ---- dark patches on the face front (eyes, mouth, nose?)
DARK = 0.25
face_dark = []
for v in bm.verts:
    p = v.co
    if p.z > -0.5 and p.y < -0.25 and v.index in vcol:   # front half of head
        r, g, b = vcol[v.index]
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        if lum < DARK:
            face_dark.append(v)

# cluster dark verts by proximity
def cluster(verts, radius=0.09):
    left = set(verts)
    out = []
    while left:
        seed = left.pop()
        cur = [seed]
        stack = [seed]
        while stack:
            a = stack.pop()
            near = [b for b in left if (a.co - b.co).length < radius]
            for b in near:
                left.discard(b)
                cur.append(b)
                stack.append(b)
        out.append(cur)
    return out

print("dark face verts:", len(face_dark))
clusters = cluster(face_dark)
clusters.sort(key=len, reverse=True)
marks = []
for i, cl in enumerate(clusters[:12]):
    c = sum((v.co for v in cl), Vector()) / len(cl)
    mn = Vector((min(v.co.x for v in cl), min(v.co.y for v in cl), min(v.co.z for v in cl)))
    mx = Vector((max(v.co.x for v in cl), max(v.co.y for v in cl), max(v.co.z for v in cl)))
    lum = sum(0.2126 * vcol[v.index][0] + 0.7152 * vcol[v.index][1] + 0.0722 * vcol[v.index][2] for v in cl) / len(cl)
    print(f"dark{i}: n={len(cl)} centre=({c.x:.3f},{c.y:.3f},{c.z:.3f}) "
          f"ext=({mx.x-mn.x:.3f},{mx.y-mn.y:.3f},{mx.z-mn.z:.3f}) lum={lum:.2f}")
    marks.append((f"d{i}", c))

# ---- ears: verts near the top, saved by connected component
print("\ntop verts by z slice (z>0.55):")
top = [v for v in bm.verts if v.co.z > 0.55]
tclusters = cluster(top, radius=0.12)
tclusters.sort(key=len, reverse=True)
for i, cl in enumerate(tclusters[:8]):
    c = sum((v.co for v in cl), Vector()) / len(cl)
    mn = Vector((min(v.co.x for v in cl), min(v.co.y for v in cl), min(v.co.z for v in cl)))
    mx = Vector((max(v.co.x for v in cl), max(v.co.y for v in cl), max(v.co.z for v in cl)))
    print(f"top{i}: n={len(cl)} centre=({c.x:.3f},{c.y:.3f},{c.z:.3f}) "
          f"x[{mn.x:.2f},{mx.x:.2f}] y[{mn.y:.2f},{mx.y:.2f}] z[{mn.z:.2f},{mx.z:.2f}]")
    marks.append((f"t{i}", c))

bm.free()

# ---- render face close-ups with markers
scene = bpy.context.scene
for o in list(scene.objects):
    if o.type in {"CAMERA", "LIGHT"}:
        bpy.data.objects.remove(o, do_unlink=True)

for name, c in marks:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.018, location=c + Vector((0, -0.03, 0)))
    sp = bpy.context.object
    m = bpy.data.materials.new("mark_" + name)
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (1, 0, 1, 1)
    sp.data.materials.append(m)

scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x = scene.render.resolution_y = 900
cam_data = bpy.data.cameras.new("C")
cam_data.type = "ORTHO"
cam = bpy.data.objects.new("C", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

views = {
    "face": (Vector((0, -0.1, 0.15)), Vector((0, -1, 0)), 1.9),
    "face_zoom": (Vector((0, -0.35, -0.1)), Vector((0, -1, 0)), 1.0),
    "ears_top": (Vector((0, 0, 0.7)), Vector((0, -1, 0.35)), 1.4),
    "ear_left_side": (Vector((0.45, 0, 0.55)), Vector((1, 0, 0)), 1.0),
    "ear_right_side": (Vector((-0.45, 0, 0.55)), Vector((-1, 0, 0)), 1.0),
}
for name, (target, d, s) in views.items():
    d = d.normalized()
    cam.location = target + d * 8
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam_data.ortho_scale = s
    scene.render.filepath = os.path.join(outdir, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("WROTE", scene.render.filepath)
