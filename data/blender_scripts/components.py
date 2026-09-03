import bpy, bmesh
from mathutils import Vector

ob = bpy.data.objects['mesh']
me = ob.data
M = ob.matrix_world
bm = bmesh.new(); bm.from_mesh(me)
bm.verts.ensure_lookup_table()

seen = set(); comps = []
for v in bm.verts:
    if v.index in seen: continue
    stack=[v]; comp=[]
    while stack:
        cur=stack.pop()
        if cur.index in seen: continue
        seen.add(cur.index); comp.append(cur)
        for e in cur.link_edges:
            o=e.other_vert(cur)
            if o.index not in seen: stack.append(o)
    comps.append(comp)
comps.sort(key=len, reverse=True)
print("components:", len(comps))
for i,c in enumerate(comps):
    ws=[M @ v.co for v in c]
    mn=Vector((min(w.x for w in ws),min(w.y for w in ws),min(w.z for w in ws)))
    mx=Vector((max(w.x for w in ws),max(w.y for w in ws),max(w.z for w in ws)))
    nb=sum(1 for v in c if any(e.is_boundary for e in v.link_edges))
    print(f"comp{i}: verts={len(c)} boundary_verts={nb} min=({mn.x:.2f},{mn.y:.2f},{mn.z:.2f}) max=({mx.x:.2f},{mx.y:.2f},{mx.z:.2f})")
bm.free()
