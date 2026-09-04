"""Data pass for the face rig: dome height profile (ear vs crown), painted eye
patch bounds via surface colour scan, and brow shell listing.
Usage: blender -b data/Semprini.blend --factory-startup --python face_data.py
"""
import bpy, bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ob = bpy.data.objects["mesh"]
bpy.ops.object.select_all(action="DESELECT")
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = ob.data

img = next(n for n in me.materials[0].node_tree.nodes if n.type == "TEX_IMAGE").image
W, H = img.size
PIX = img.pixels[:]

bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()
uvl = bm.loops.layers.uv.active

bm_tri = bm.copy()
import bmesh as _b
_b.ops.triangulate(bm_tri, faces=bm_tri.faces[:])
bm_tri.faces.ensure_lookup_table()
bvh = BVHTree.FromBMesh(bm_tri)
uvt = bm_tri.loops.layers.uv.active

from mathutils import geometry

def colour_at(loc, fidx):
    f = bm_tri.faces[fidx]
    l = f.loops
    uv = geometry.barycentric_transform(
        loc, l[0].vert.co, l[1].vert.co, l[2].vert.co,
        Vector((l[0][uvt].uv.x, l[0][uvt].uv.y, 0)),
        Vector((l[1][uvt].uv.x, l[1][uvt].uv.y, 0)),
        Vector((l[2][uvt].uv.x, l[2][uvt].uv.y, 0)))
    x = int(uv.x * W) % W
    y = int(uv.y * H) % H
    i = (y * W + x) * 4
    return (PIX[i], PIX[i + 1], PIX[i + 2])

# ---- dome (largest shell above z 0) height profile by x-bin
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
comps.sort(key=len, reverse=True)
dome = max(comps, key=lambda c: sum(1 for v in c if v.co.z > 0.3))
print(f"dome: n={len(dome)}")
print("dome max z by x bin (0.1):")
import collections
mx = collections.defaultdict(lambda: -9)
for v in dome:
    b = round(v.co.x, 1)
    mx[b] = max(mx[b], v.co.z)
for b in sorted(mx):
    print(f"  x={b:+.1f}: zmax={mx[b]:.2f}")

# ---- ear fold (+x side): verts x>0.4 by z bin
print("dome verts x>0.40 by z bin:")
cnt = collections.defaultdict(int)
for v in dome:
    if v.co.x > 0.40:
        cnt[round(v.co.z, 1)] += 1
for b in sorted(cnt):
    print(f"  z={b:+.1f}: n={cnt[b]}")

# ---- painted eye scan: ray-cast grid from -y, sample colour, report dark patch bounds
def eye_scan(x0, x1, z0, z1, name):
    hits = []
    N = 40
    for i in range(N):
        for j in range(N):
            x = x0 + (x1 - x0) * i / (N - 1)
            z = z0 + (z1 - z0) * j / (N - 1)
            loc, nrm, fidx, dist = bvh.ray_cast(Vector((x, -2.0, z)), Vector((0, 1, 0)), 3.0)
            if loc is None:
                continue
            r, g, b = colour_at(loc, fidx)
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            if lum < 0.35:
                hits.append((x, z, loc.y, lum))
    if not hits:
        print(f"{name}: no dark hits")
        return
    xs = [h[0] for h in hits]
    zs = [h[1] for h in hits]
    ys = [h[2] for h in hits]
    print(f"{name}: n={len(hits)} x[{min(xs):.3f},{max(xs):.3f}] z[{min(zs):.3f},{max(zs):.3f}] "
          f"y_surface[{min(ys):.3f},{max(ys):.3f}] centre=({(min(xs)+max(xs))/2:.3f},{(min(zs)+max(zs))/2:.3f})")

eye_scan(-0.45, -0.10, 0.25, 0.60, "eyeR_painted")
eye_scan(0.00, 0.30, 0.10, 0.50, "eyeL_painted")

# ---- small shells near each eye (brow/lash geometry)
for name, ex, ez in (("browR", -0.28, 0.48), ("browL", 0.14, 0.38)):
    print(f"{name} nearby shells:")
    for ci, comp in enumerate(comps):
        if len(comp) > 120 or len(comp) < 3:
            continue
        c = sum((v.co for v in comp), Vector()) / len(comp)
        if abs(c.x - ex) < 0.18 and abs(c.z - ez) < 0.18 and c.y < -0.2:
            mn = Vector((min(v.co.x for v in comp), min(v.co.y for v in comp), min(v.co.z for v in comp)))
            mxx = Vector((max(v.co.x for v in comp), max(v.co.y for v in comp), max(v.co.z for v in comp)))
            print(f"  comp n={len(comp)} centre=({c.x:.3f},{c.y:.3f},{c.z:.3f}) z[{mn.z:.2f},{mxx.z:.2f}] x[{mn.x:.2f},{mxx.x:.2f}]")

bm.free()
bm_tri.free()
