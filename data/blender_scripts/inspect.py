import bpy
from mathutils import Vector

print("=== SCENE ===", bpy.context.scene.name)
for ob in bpy.data.objects:
    print(f"OBJ {ob.name!r} type={ob.type} parent={ob.parent.name if ob.parent else None} "
          f"loc={tuple(round(v,3) for v in ob.location)} rot={tuple(round(v,3) for v in ob.rotation_euler)} "
          f"scale={tuple(round(v,3) for v in ob.scale)} hide={ob.hide_render}")
    if ob.type == 'MESH':
        me = ob.data
        print(f"   mesh={me.name!r} verts={len(me.vertices)} edges={len(me.edges)} faces={len(me.polygons)}")
        bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        mn = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
        mx = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
        print(f"   world bbox min={tuple(round(v,3) for v in mn)} max={tuple(round(v,3) for v in mx)}")
        print(f"   materials={[m.name if m else None for m in me.materials]}")
        print(f"   modifiers={[(m.name, m.type) for m in ob.modifiers]}")
        print(f"   vgroups={[g.name for g in ob.vertex_groups]}")
        print(f"   shape_keys={[k.name for k in me.shape_keys.key_blocks] if me.shape_keys else None}")
        # boundary (open) edges -> where arms are cut
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(me)
        bound = [e for e in bm.edges if e.is_boundary]
        print(f"   boundary_edges={len(bound)}")
        # cluster boundary loops
        seen = set()
        loops = []
        for e in bound:
            if e.index in seen:
                continue
            stack = [e]
            loop = []
            while stack:
                cur = stack.pop()
                if cur.index in seen:
                    continue
                seen.add(cur.index)
                loop.append(cur)
                for v in cur.verts:
                    for le in v.link_edges:
                        if le.is_boundary and le.index not in seen:
                            stack.append(le)
            loops.append(loop)
        for i, loop in enumerate(loops):
            vs = {v for e in loop for v in e.verts}
            c = sum((ob.matrix_world @ v.co for v in vs), Vector()) / len(vs)
            r = max(((ob.matrix_world @ v.co) - c).length for v in vs)
            print(f"   loop{i}: edges={len(loop)} verts={len(vs)} center={tuple(round(x,3) for x in c)} radius={r:.3f}")
        bm.free()
    if ob.type == 'ARMATURE':
        for b in ob.data.bones:
            print(f"   bone {b.name} head={tuple(round(v,3) for v in b.head_local)} tail={tuple(round(v,3) for v in b.tail_local)} parent={b.parent.name if b.parent else None}")

print("=== MATERIALS ===")
for m in bpy.data.materials:
    print(m.name, "nodes" if m.use_nodes else "", [n.type for n in m.node_tree.nodes] if m.use_nodes else "")
print("=== IMAGES ===")
for im in bpy.data.images:
    print(im.name, im.size[:], im.filepath)
print("=== COLLECTIONS ===")
for c in bpy.data.collections:
    print(c.name, [o.name for o in c.objects])
print("=== ACTIONS ===", [a.name for a in bpy.data.actions])
