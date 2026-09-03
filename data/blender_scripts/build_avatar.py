"""Complete the Semprini avatar's arms, rig it with an IK-capable armature and export a GLB.

Usage:
  blender -b data/Semprini.blend --factory-startup --python data/blender_scripts/build_avatar.py -- \
      data/Semprini_rigged.blend app/static/models/glb/semprini_avatar.glb

Coordinate notes (Blender, Z up, character faces -Y):
  +X is the character's LEFT (.L suffix), -X is its RIGHT (.R suffix).
"""
import sys, math, os, struct, zlib
import bpy, bmesh
from mathutils import Vector, Matrix, Quaternion, geometry
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT_BLEND = argv[0] if len(argv) > 0 else "/tmp/Semprini_rigged.blend"
OUT_GLB = argv[1] if len(argv) > 1 else "/tmp/semprini_avatar.glb"

# ---------------------------------------------------------------- parameters
Z_CUT = -1.0            # existing arms end here (elbow)
Z_NECK = -0.63          # head / torso split
Z_SHOULDER = -0.72      # shoulder joint height
ARM_X_MIN = {"L": 0.27, "R": -0.47}   # torso/arm split (x > for L, x < for R)
ARM_BLEND = 0.07        # half-width of the torso/arm weight blend band
RING_N = 24
ELBOW_STEPS = 6
FOREARM_STEPS = 5
PAW_STEPS = 9
FOREARM_LEN = 0.36
PAW_LEN = 0.30
BEND_DEG = 62.0         # forearm rotates this much forward from straight down
OUTWARD = 0.18          # sideways component of the forearm direction
PAW_SCALE = 1.28        # paw radius relative to wrist
PAW_FLATTEN = 0.82
PAW_DARKEN = 0.72

# ---------------------------------------------------------------- helpers
def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def circular_smooth(vals, passes=2):
    n = len(vals)
    for _ in range(passes):
        vals = [(vals[i - 1] + 2 * vals[i] + vals[(i + 1) % n]) / 4 for i in range(n)]
    return vals

# ---------------------------------------------------------------- scene prep
scene = bpy.context.scene
mesh_ob = bpy.data.objects["mesh"]
mesh_ob.name = "SempriniAvatar"
for o in list(scene.objects):
    if o.type in {"CAMERA", "LIGHT"}:
        bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.object.select_all(action="DESELECT")
mesh_ob.select_set(True)
bpy.context.view_layer.objects.active = mesh_ob
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = mesh_ob.data

mat0 = me.materials[0]
bsdf0 = next(n for n in mat0.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
tex_img = next(n for n in mat0.node_tree.nodes if n.type == "TEX_IMAGE").image
print("mat0 roughness", bsdf0.inputs["Roughness"].default_value,
      "metallic", bsdf0.inputs["Metallic"].default_value, "image", tex_img.name, tex_img.size[:])

# ---------------------------------------------------------------- analyse stumps
bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()
uv_layer = bm.loops.layers.uv.active

# Triangulated copy for BVH / UV lookup
bm_tri = bm.copy()
bmesh.ops.triangulate(bm_tri, faces=bm_tri.faces[:])
bm_tri.faces.ensure_lookup_table()
bvh = BVHTree.FromBMesh(bm_tri)
uv_tri = bm_tri.loops.layers.uv.active

W, H = tex_img.size
PIX = tex_img.pixels[:]

def sample_tex(uv):
    x = int(uv.x * W) % W
    y = int(uv.y * H) % H
    i = (y * W + x) * 4
    return Vector((srgb_to_linear(PIX[i]), srgb_to_linear(PIX[i + 1]), srgb_to_linear(PIX[i + 2])))

def colour_at_hit(loc, fidx):
    f = bm_tri.faces[fidx]
    l = f.loops
    uv = geometry.barycentric_transform(
        loc, l[0].vert.co, l[1].vert.co, l[2].vert.co,
        Vector((l[0][uv_tri].uv.x, l[0][uv_tri].uv.y, 0)),
        Vector((l[1][uv_tri].uv.x, l[1][uv_tri].uv.y, 0)),
        Vector((l[2][uv_tri].uv.x, l[2][uv_tri].uv.y, 0)))
    return sample_tex(uv)

def arm_verts(side):
    if side == "L":
        return [v for v in bm.verts if v.co.x > ARM_X_MIN["L"] and v.co.z < Z_NECK - 0.02]
    return [v for v in bm.verts if v.co.x < ARM_X_MIN["R"] and v.co.z < Z_NECK - 0.02]

def stump_centre(side):
    vs = [v.co for v in arm_verts(side) if v.co.z < Z_CUT + 0.1]
    xs = [v.x for v in vs]; ys = [v.y for v in vs]
    return Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0))

def radial_profile(centre, z, n):
    """Return (radii, colours) for n angles around centre at height z."""
    radii, cols = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        d = Vector((math.cos(a), math.sin(a), 0))
        o = Vector((centre.x, centre.y, z))
        loc, nrm, fidx, dist = bvh.ray_cast(o, d, 0.32)
        if loc is None:
            radii.append(None); cols.append(None)
        else:
            radii.append(dist)
            # sample colour just above the cut so the new geometry matches the visible edge
            c = None
            for zc in (Z_CUT + 0.01, Z_CUT + 0.03, Z_CUT + 0.05):
                l2, _, f2, _ = bvh.ray_cast(Vector((centre.x, centre.y, zc)), d, 0.32)
                if l2 is not None:
                    c = colour_at_hit(l2, f2) if c is None else (c + colour_at_hit(l2, f2))
            cols.append(c / 3 if c is not None else colour_at_hit(loc, fidx))
    # fill gaps
    valid = [r for r in radii if r is not None]
    med = sorted(valid)[len(valid) // 2]
    radii = [min(max(r, med * 0.75), med * 1.25) if r is not None else med for r in radii]
    radii = circular_smooth(radii)
    mean_col = sum((c for c in cols if c is not None), Vector()) / max(1, sum(1 for c in cols if c is not None))
    cols = [c if c is not None else mean_col for c in cols]
    cols = [(cols[i - 1] + 2 * cols[i] + cols[(i + 1) % n]) / 4 for i in range(n)]
    return radii, cols

# ---------------------------------------------------------------- build new arm geometry
# Arm colours are baked into a small texture: u = angle around the arm, v = position
# along the arm (one texel row per ring), left half for .L and right half for .R.
TEX_ROWS = 2 + ELBOW_STEPS + FOREARM_STEPS + PAW_STEPS + 1
SIDE_W = RING_N + 1                     # +1: duplicated seam column
ARM_TEX_W, ARM_TEX_H = SIDE_W * 2, TEX_ROWS
arm_px = [0.0] * (ARM_TEX_W * ARM_TEX_H * 4)     # linear RGBA floats, row 0 = bottom
ARM_TEX_PATH = os.path.splitext(OUT_BLEND)[0] + "_arms.png"

def put_texel(x, y, col):
    i = (y * ARM_TEX_W + x) * 4
    arm_px[i:i + 4] = [col.x, col.y, col.z, 1.0]

def linear_to_srgb(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055

def write_png(path, w, h, px):
    """px: linear RGBA floats, row 0 at the bottom (Blender/GL convention)."""
    raw = bytearray()
    for y in range(h - 1, -1, -1):
        raw.append(0)
        for x in range(w):
            i = (y * w + x) * 4
            raw.extend(int(round(linear_to_srgb(px[i + k]) * 255)) for k in range(3))
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))

mat_arms = bpy.data.materials.new("mat_arms")
mat_arms.use_nodes = True
nt = mat_arms.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
texn = nt.nodes.new("ShaderNodeTexImage")
texn.interpolation = "Linear"
nt.links.new(texn.outputs["Color"], bsdf.inputs["Base Color"])
nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
bsdf.inputs["Roughness"].default_value = bsdf0.inputs["Roughness"].default_value
bsdf.inputs["Metallic"].default_value = bsdf0.inputs["Metallic"].default_value
me.materials.append(mat_arms)
ARM_MAT_INDEX = len(me.materials) - 1

new_vert_weights = {}   # BMVert -> {bone_name: weight}
ring_uv = {}            # BMVert -> (u_index, v_row) ; u_index in 0..RING_N
joints = {}             # side -> dict(shoulder, elbow, wrist, tip)

def add_ring(centre, frame_x, frame_y, radii, scale_x, scale_y, cols, weights, side, row):
    verts = []
    x0 = 0 if side == "L" else SIDE_W
    for i in range(RING_N):
        a = 2 * math.pi * i / RING_N
        off = frame_x * (math.cos(a) * radii[i] * scale_x) + frame_y * (math.sin(a) * radii[i] * scale_y)
        v = bm.verts.new(centre + off)
        new_vert_weights[v] = weights
        ring_uv[v] = (x0 + i, row)
        put_texel(x0 + i, row, cols[i])
        verts.append(v)
    put_texel(x0 + RING_N, row, cols[0])
    return verts

def bridge(r0, r1):
    faces = []
    for i in range(RING_N):
        f = bm.faces.new((r0[i], r0[(i + 1) % RING_N], r1[(i + 1) % RING_N], r1[i]))
        f.material_index = ARM_MAT_INDEX
        f.smooth = True
        # the i == RING_N-1 quad wraps around the seam; let its far edge use u of the
        # next texel instead of wrapping to u=0 (the texel row is periodic anyway)
        for l in f.loops:
            x, row = ring_uv[l.vert]
            side_x0 = (x // SIDE_W) * SIDE_W
            local = x - side_x0
            if i == RING_N - 1 and local == 0:
                local = RING_N
            l[uv_layer].uv = ((side_x0 + local + 0.5) / ARM_TEX_W, (row + 0.5) / ARM_TEX_H)
        faces.append(f)
    return faces

def build_arm(side):
    s = 1.0 if side == "L" else -1.0
    centre = stump_centre(side)
    radii, cols = radial_profile(centre, Z_CUT + 0.07, RING_N)
    r_mean = sum(radii) / len(radii)
    print(f"arm {side}: centre=({centre.x:.3f},{centre.y:.3f}) r_mean={r_mean:.3f} "
          f"r_min={min(radii):.3f} r_max={max(radii):.3f} col_mean={sum(cols, Vector())/len(cols)}")

    elbow = Vector((centre.x, centre.y, Z_CUT))
    down = Vector((0, 0, -1))
    fwd = Vector((s * OUTWARD, -1.0, 0)).normalized()
    beta = math.radians(BEND_DEG)
    axis = down.cross(fwd).normalized()   # rotate 'down' towards 'fwd'
    fdir = Matrix.Rotation(beta, 3, axis) @ down   # final forearm direction

    ex, ey = Vector((1, 0, 0)), Vector((0, 1, 0))
    up_arm, fore, hand = f"UpperArm.{side}", f"ForeArm.{side}", f"Hand.{side}"

    rings = []
    row = 0
    # start inside the existing stump so the seam is hidden
    rings.append(add_ring(Vector((centre.x, centre.y, Z_CUT + 0.07)), ex, ey, [r * 0.965 for r in radii], 1, 1, cols,
                          {up_arm: 1.0}, side, row)); row += 1
    rings.append(add_ring(Vector((centre.x, centre.y, Z_CUT + 0.02)), ex, ey, [r * 0.985 for r in radii], 1, 1, cols,
                          {up_arm: 1.0}, side, row)); row += 1

    # elbow: circular arc of radius R_b bending from 'down' to fdir
    R_b = r_mean * 1.15
    m = axis.cross(down).normalized()     # in-plane direction towards the arc centre
    Cb = elbow + m * R_b
    for k in range(1, ELBOW_STEPS + 1):
        phi = beta * k / ELBOW_STEPS
        rot = Matrix.Rotation(phi, 3, axis)
        p = Cb + rot @ (-m * R_b)
        t = k / ELBOW_STEPS
        w_fore = smoothstep((t - 0.15) / 0.7)
        rings.append(add_ring(p, rot @ ex, rot @ ey, radii, 1, 1, cols, {up_arm: 1 - w_fore, fore: w_fore}, side, row))
        row += 1
    rot_f = Matrix.Rotation(beta, 3, axis)
    fx, fy = rot_f @ ex, rot_f @ ey
    elbow_end = Cb + rot_f @ (-m * R_b)

    # forearm: straight, slight taper
    for k in range(1, FOREARM_STEPS + 1):
        t = k / FOREARM_STEPS
        p = elbow_end + fdir * (FOREARM_LEN * t)
        taper = 1.0 - 0.13 * t
        w_hand = smoothstep((t - 0.75) / 0.25) * 0.5
        rings.append(add_ring(p, fx, fy, radii, taper, taper, cols, {fore: 1 - w_hand, hand: w_hand}, side, row))
        row += 1
    wrist = elbow_end + fdir * FOREARM_LEN
    r_wrist = r_mean * 0.87

    # paw: rounded mitten, darker
    paw_cols = [c * PAW_DARKEN for c in cols]
    circ = [r_wrist] * RING_N
    last_ring = None
    for k in range(1, PAW_STEPS + 1):
        t = k / PAW_STEPS
        # bulge then hemispherical close
        if t < 0.45:
            sc = 1.0 + (PAW_SCALE - 1.0) * smoothstep(t / 0.45)
        else:
            u = (t - 0.45) / 0.55
            sc = PAW_SCALE * math.sqrt(max(0.0, 1 - u * u))
        sc = max(sc, 0.06)
        blend = smoothstep(t / 0.3)
        c_here = [cols[i].lerp(paw_cols[i], blend) for i in range(RING_N)]
        p = wrist + fdir * (PAW_LEN * t)
        w_hand = 0.5 + 0.5 * smoothstep(t / 0.3)
        ring = add_ring(p, fx, fy, circ, sc, sc * PAW_FLATTEN, c_here, {fore: 1 - w_hand, hand: w_hand}, side, row)
        row += 1
        rings.append(ring)
        last_ring = ring
    tip = wrist + fdir * (PAW_LEN * 1.02)
    tip_v = bm.verts.new(tip)
    new_vert_weights[tip_v] = {hand: 1.0}
    x0 = 0 if side == "L" else SIDE_W
    for i in range(RING_N + 1):
        put_texel(x0 + i, row, paw_cols[i % RING_N])
    ring_uv[tip_v] = (x0, row)

    for a, b in zip(rings, rings[1:]):
        bridge(a, b)
    for i in range(RING_N):
        f = bm.faces.new((last_ring[i], last_ring[(i + 1) % RING_N], tip_v))
        f.material_index = ARM_MAT_INDEX
        f.smooth = True
        for l in f.loops:
            x, r_ = ring_uv[l.vert]
            local = x - x0
            if l.vert is tip_v:
                local = i + 0.5
            elif i == RING_N - 1 and local == 0:
                local = RING_N
            l[uv_layer].uv = ((x0 + local + 0.5) / ARM_TEX_W, (r_ + 0.5) / ARM_TEX_H)

    shoulder = Vector((centre.x - s * 0.02, centre.y, Z_SHOULDER))
    joints[side] = dict(shoulder=shoulder, elbow=elbow, wrist=wrist, tip=tip, fdir=fdir, r=r_mean)

build_arm("L")
build_arm("R")

bm.verts.index_update()
bmesh.ops.recalc_face_normals(bm, faces=[f for f in bm.faces if f.material_index == ARM_MAT_INDEX])
bm.to_mesh(me)
me.update()

write_png(ARM_TEX_PATH, ARM_TEX_W, ARM_TEX_H, arm_px)
arm_img = bpy.data.images.load(ARM_TEX_PATH)
arm_img.name = "semprini_arms"
arm_img.colorspace_settings.name = "sRGB"
arm_img.pack()
texn.image = arm_img
print("arm texture", ARM_TEX_PATH, arm_img.size[:])

# ---------------------------------------------------------------- vertex groups (weights)
bone_names = ["Torso", "Head", "UpperArm.L", "ForeArm.L", "Hand.L", "UpperArm.R", "ForeArm.R", "Hand.R"]
vgs = {n: mesh_ob.vertex_groups.new(name=n) for n in bone_names}

new_idx_weights = {v.index: w for v, w in new_vert_weights.items()}
BLEND = 0.03
for v in me.vertices:
    i = v.index
    if i in new_idx_weights:
        for n, w in new_idx_weights[i].items():
            if w > 1e-4:
                vgs[n].add([i], w, "REPLACE")
        continue
    p = v.co
    if p.z > Z_NECK + BLEND:
        vgs["Head"].add([i], 1.0, "REPLACE")
        continue
    # head/torso blend band
    w_head = smoothstep((p.z - (Z_NECK - BLEND)) / (2 * BLEND))
    # torso/arm blend band (soft in x so shoulder rotation doesn't tear the seam)
    w_arm_L = smoothstep((p.x - (ARM_X_MIN["L"] - ARM_BLEND)) / (2 * ARM_BLEND))
    w_arm_R = smoothstep(((ARM_X_MIN["R"] + ARM_BLEND) - p.x) / (2 * ARM_BLEND))
    w_body = 1 - w_head
    weights = {
        "Head": w_head,
        "UpperArm.L": w_body * w_arm_L,
        "UpperArm.R": w_body * w_arm_R,
        "Torso": w_body * (1 - w_arm_L - w_arm_R),
    }
    for n, w in weights.items():
        if w > 1e-4:
            vgs[n].add([i], w, "REPLACE")

bm.free(); bm_tri.free()

# ---------------------------------------------------------------- armature
arm_data = bpy.data.armatures.new("SempriniRig")
rig = bpy.data.objects.new("SempriniRig", arm_data)
scene.collection.objects.link(rig)
bpy.ops.object.select_all(action="DESELECT")
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")

eb = arm_data.edit_bones
def bone(name, head, tail, parent=None, connect=False, deform=True):
    b = eb.new(name)
    b.head, b.tail = head, tail
    b.use_deform = deform
    if parent:
        b.parent = eb[parent]
        b.use_connect = connect
    return b

TORSO_BASE = Vector((-0.1, -0.15, Z_CUT))
NECK = Vector((-0.05, -0.15, Z_NECK + 0.04))
bone("Torso", TORSO_BASE, NECK)
bone("Head", NECK, NECK + Vector((0, 0, 0.9)), "Torso", connect=True)
for side in ("L", "R"):
    j = joints[side]
    bone(f"UpperArm.{side}", j["shoulder"], j["elbow"], "Torso")
    bone(f"ForeArm.{side}", j["elbow"], j["wrist"], f"UpperArm.{side}", connect=True)
    bone(f"Hand.{side}", j["wrist"], j["tip"], f"ForeArm.{side}", connect=True)
    # IK control: sits at the wrist, parented to the torso so it follows the body
    bone(f"IK_Hand.{side}", j["wrist"], j["wrist"] + Vector((0, 0, -0.12)), "Torso", deform=False)
look = Vector((-0.05, -1.6, -0.2))
bone("LookTarget", look, look + Vector((0, 0, 0.12)), "Torso", deform=False)

bpy.ops.object.mode_set(mode="POSE")
pb = rig.pose.bones
for side in ("L", "R"):
    c = pb[f"ForeArm.{side}"].constraints.new("IK")
    c.target = rig
    c.subtarget = f"IK_Hand.{side}"
    c.chain_count = 2
    c.use_stretch = False
    c.iterations = 50
    pb[f"ForeArm.{side}"].lock_ik_x = False
    pb[f"ForeArm.{side}"].use_ik_limit_x = True
    pb[f"ForeArm.{side}"].ik_min_x = math.radians(-150)
    pb[f"ForeArm.{side}"].ik_max_x = math.radians(5)
    pb[f"ForeArm.{side}"].lock_ik_y = True
    pb[f"ForeArm.{side}"].lock_ik_z = True

# Head: damped-track towards LookTarget along whichever local axis points forward (-Y world)
head_mat = rig.matrix_world @ pb["Head"].matrix
forward = Vector((0, -1, 0))
best = max(("X", "Y", "Z", "-X", "-Y", "-Z"),
           key=lambda ax: (-1 if ax.startswith("-") else 1) * (head_mat.to_3x3() @ Vector(
               (1 if ax.endswith("X") else 0, 1 if ax.endswith("Y") else 0, 1 if ax.endswith("Z") else 0))).dot(forward))
trk = pb["Head"].constraints.new("DAMPED_TRACK")
trk.target = rig
trk.subtarget = "LookTarget"
trk.track_axis = "TRACK_" + ("NEGATIVE_" + best[1] if best.startswith("-") else best)
trk.influence = 0.6
print("Head track axis:", trk.track_axis)
bpy.ops.object.mode_set(mode="OBJECT")

# parent mesh to rig with armature modifier
mesh_ob.parent = rig
mod = mesh_ob.modifiers.new("Armature", "ARMATURE")
mod.object = rig
mod.use_vertex_groups = True

# ---------------------------------------------------------------- save + export
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print("SAVED", OUT_BLEND)

bpy.ops.object.select_all(action="DESELECT")
rig.select_set(True); mesh_ob.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.gltf(
    filepath=OUT_GLB,
    export_format="GLB",
    use_selection=True,
    export_apply=True,
    export_yup=True,
    export_skins=True,
    export_def_bones=False,
    export_animations=False,
    export_rest_position_armature=True,
    export_materials="EXPORT",
    export_image_format="AUTO",
    export_texcoords=True,
    export_normals=True,
)
print("EXPORTED", OUT_GLB)
for side in ("L", "R"):
    j = joints[side]
    print(f"JOINTS {side}: shoulder={tuple(round(x,3) for x in j['shoulder'])} elbow={tuple(round(x,3) for x in j['elbow'])} "
          f"wrist={tuple(round(x,3) for x in j['wrist'])} tip={tuple(round(x,3) for x in j['tip'])}")
