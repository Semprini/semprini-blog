import bpy, bmesh
from mathutils import Vector

ob = bpy.data.objects['mesh']
me = ob.data
M = ob.matrix_world
bm = bmesh.new(); bm.from_mesh(me)
uv_layer = bm.loops.layers.uv.active

# Boundary verts at the bottom cut plane
cut = [v for v in bm.verts if (M @ v.co).z < -0.985 and any(e.is_boundary for e in v.link_edges)]
print("bottom boundary verts:", len(cut))
xs = sorted((M @ v.co).x for v in cut)
print("x histogram (0.1 bins):")
import collections
h = collections.Counter(round(x, 1) for x in xs)
for k in sorted(h): print(f"  x={k:+.1f}: {h[k]}")

# Cluster bottom boundary verts into connected boundary loops
seen=set(); loops=[]
for v in cut:
    if v.index in seen: continue
    stack=[v]; loop=[]
    while stack:
        cur=stack.pop()
        if cur.index in seen: continue
        seen.add(cur.index); loop.append(cur)
        for e in cur.link_edges:
            if e.is_boundary:
                o=e.other_vert(cur)
                if o.index not in seen and (M @ o.co).z < -0.985:
                    stack.append(o)
    loops.append(loop)
for i,loop in enumerate(loops):
    ws=[M @ v.co for v in loop]
    c=sum(ws,Vector())/len(ws)
    mnx=min(w.x for w in ws); mxx=max(w.x for w in ws); mny=min(w.y for w in ws); mxy=max(w.y for w in ws)
    print(f"loop{i}: n={len(loop)} center=({c.x:.3f},{c.y:.3f},{c.z:.3f}) x[{mnx:.3f},{mxx:.3f}] y[{mny:.3f},{mxy:.3f}]")
    # UV sample
    uvs=[l[uv_layer].uv.copy() for v in loop for l in v.link_loops]
    if uvs:
        mu=sum(uvs,Vector((0,0)))/len(uvs)
        print(f"   mean uv=({mu.x:.3f},{mu.y:.3f})")

# Arm cross sections at several heights (all verts, not just boundary), split by |x|>0.3
print("\nArm verts by z slice (|x|>0.35):")
for z0 in [-1.0,-0.9,-0.8,-0.7,-0.6,-0.5,-0.4]:
    for side,sgn in (("L(-x)",-1),("R(+x)",1)):
        vs=[M @ v.co for v in bm.verts if abs((M@v.co).z - z0) < 0.05 and sgn*(M@v.co).x > 0.35]
        if vs:
            c=sum(vs,Vector())/len(vs)
            print(f"  z={z0:+.1f} {side}: n={len(vs)} center=({c.x:.3f},{c.y:.3f}) x[{min(v.x for v in vs):.2f},{max(v.x for v in vs):.2f}] y[{min(v.y for v in vs):.2f},{max(v.y for v in vs):.2f}]")

# Torso/neck slices
print("\nAll verts by z slice (|x|<0.35):")
for z0 in [-1.0,-0.8,-0.6,-0.5,-0.4,-0.3,-0.2]:
    vs=[M @ v.co for v in bm.verts if abs((M@v.co).z - z0) < 0.03 and abs((M@v.co).x) < 0.35]
    if vs:
        print(f"  z={z0:+.1f}: n={len(vs)} x[{min(v.x for v in vs):.2f},{max(v.x for v in vs):.2f}] y[{min(v.y for v in vs):.2f},{max(v.y for v in vs):.2f}]")

# sample texture colour at mean UV of each bottom loop
img = None
for n in me.materials[0].node_tree.nodes:
    if n.type=='TEX_IMAGE': img=n.image
print("\nimage:", img.name, img.size[:])
w,h=img.size
px=img.pixels[:]
def sample(u,v):
    x=int(u*w)%w; y=int(v*h)%h; i=(y*w+x)*4
    return tuple(round(px[i+k],3) for k in range(3))
for i,loop in enumerate(loops):
    uvs=[l[uv_layer].uv.copy() for v in loop for l in v.link_loops]
    mu=sum(uvs,Vector((0,0)))/len(uvs)
    print(f"loop{i} colour at mean uv: {sample(mu.x,mu.y)}; samples:", [sample(u.x,u.y) for u in uvs[::max(1,len(uvs)//5)]])
bm.free()
