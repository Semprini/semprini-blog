"""Find see-through holes around the mouth: cast rays from the front and report
where the first hit is far behind the muzzle surface."""
import bpy, bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ob = bpy.data.objects["mesh"]
bpy.ops.object.select_all(action="DESELECT")
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bm = bmesh.new(); bm.from_mesh(ob.data)
bmesh.ops.triangulate(bm, faces=bm.faces[:])
bvh = BVHTree.FromBMesh(bm)

N = 30
xs = [-0.36 + 0.30 * i / (N - 1) for i in range(N)]
zs = [-0.48 - 0.20 * j / (N - 1) for j in range(N)]
holes = []
print("first-hit y (x10, clipped) around the mouth; '##' = through to the back of the head:")
for z in zs:
    row = ""
    for x in xs:
        loc, n, f, d = bvh.ray_cast(Vector((x, -2.0, z)), Vector((0, 1, 0)), 4.0)
        y = loc.y if loc else 9
        if y > -0.2:
            row += "##"
            holes.append((x, z, y))
        else:
            row += f"{int(-y * 10):2d}"
    print(f"z={z:+.3f} {row}")
if holes:
    hx = [h[0] for h in holes]; hz = [h[1] for h in holes]
    print(f"holes: n={len(holes)} x[{min(hx):.3f},{max(hx):.3f}] z[{min(hz):.3f},{max(hz):.3f}]")
    # neighbourhood surface y around the hole for the fill placement
    ys = []
    for (x, z, _y) in holes:
        for dx, dz in ((-0.03, 0), (0.03, 0), (0, -0.03), (0, 0.03)):
            loc, n, f, d = bvh.ray_cast(Vector((x + dx, -2.0, z + dz)), Vector((0, 1, 0)), 4.0)
            if loc and loc.y < -0.55:
                ys.append(loc.y)
    if ys:
        print(f"surface y around holes: [{min(ys):.3f},{max(ys):.3f}]")
