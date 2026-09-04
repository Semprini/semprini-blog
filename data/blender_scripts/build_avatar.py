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

# Face features (coordinates from data/blender_scripts/face_data.py analysis)
EYE = {  # painted-on eye patches on the head dome: x0, x1, z_top, z_bot
    "R": (-0.39, -0.17, 0.465, 0.23),
    "L": (0.02, 0.23, 0.395, 0.10),
}
LID_INSET = 0.014       # eyelid patch offset in front of the surface
LID_NX, LID_NZ = 11, 9
MOUTH_C = Vector((-0.213, -0.672, -0.558))   # small dark indent shell centroid (lip line)
MOUTH_W, MOUTH_H = 0.085, 0.045              # open-mouth patch half extents; chin ends ~0.09 below the lip
MOUTH_INSET = 0.012
MOUTH_NX, MOUTH_NZ = 11, 7
EAR_R_PIVOT = Vector((-0.47, -0.05, 0.75))   # up ear: root where the cup leaves the dome
EAR_R_TIP = Vector((-0.56, -0.04, 0.98))
EAR_L_PIVOT = Vector((0.45, -0.03, 0.62))    # folded ear: root at the side of the head
EAR_L_TIP = Vector((0.62, -0.10, 0.28))

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

# ---------------------------------------------------------------- face feature shells
# The model is a pile of overlapping shells; classify them before new geometry is added.
_seen = set()
_comps = []
for _v in bm.verts:
    if _v.index in _seen:
        continue
    _stack = [_v]
    _comp = []
    while _stack:
        _cur = _stack.pop()
        if _cur.index in _seen:
            continue
        _seen.add(_cur.index)
        _comp.append(_cur)
        for _e in _cur.link_edges:
            _o = _e.other_vert(_cur)
            if _o.index not in _seen:
                _stack.append(_o)
    _comps.append(_comp)

dome_comp = max(_comps, key=lambda c: sum(1 for v in c if v.co.z > 0.3))
dome_idx = {v.index for v in dome_comp}

feature_idx = {"Brow.R": set(), "Brow.L": set(), "Ear.L": set(), "Ear.R": set()}
for _comp in _comps:
    if _comp is dome_comp:
        continue
    n = len(_comp)
    c = sum((v.co for v in _comp), Vector()) / n
    idxs = {v.index for v in _comp}
    if n <= 40 and -0.38 < c.x < -0.18 and 0.44 < c.z < 0.52 and c.y < -0.2:
        feature_idx["Brow.R"] |= idxs        # black brow arc + lash strips
    elif n <= 40 and 0.02 < c.x < 0.24 and 0.36 < c.z < 0.47 and c.y < -0.2:
        feature_idx["Brow.L"] |= idxs
    elif n <= 130 and c.x > 0.42 and 0.08 < c.z < 0.66:
        feature_idx["Ear.L"] |= idxs         # folded ear flap shells
    elif n <= 130 and c.x < -0.32 and c.z > 0.60:
        feature_idx["Ear.R"] |= idxs         # up ear trim shells
for k, s in feature_idx.items():
    print(f"feature {k}: {len(s)} verts")

def ear_weight(p):
    """Spatial ear membership with a soft base, independent of which shell a vertex is on."""
    # up ear (.R): everything high on the -x side of the dome
    w_r = smoothstep((-0.26 - p.x) / 0.20) * smoothstep((p.z - 0.60) / 0.20)
    # folded ear (.L): the flap hanging off the +x side, front half only
    w_l = (smoothstep((p.x - 0.34) / 0.16)
           * smoothstep((p.z - 0.04) / 0.12) * smoothstep((0.72 - p.z) / 0.10)
           * smoothstep((0.18 - p.y) / 0.14))
    return w_l, w_r

new_vert_weights = {}   # BMVert -> {bone_name: weight}

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
TEX_ROWS_ARM = 2 + ELBOW_STEPS + FOREARM_STEPS + PAW_STEPS + 1
LID_ROW = {"L": TEX_ROWS_ARM, "R": TEX_ROWS_ARM + 2}   # two rows per lid: top / bottom shade
TEX_ROWS = TEX_ROWS_ARM + 4
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

def flat_material(name, rgb, roughness=0.6):
    """Untextured material; JS finds the mouth parts by these names."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = roughness
    m.diffuse_color = (*rgb, 1.0)
    me.materials.append(m)
    return len(me.materials) - 1

MOUTH_MASK_MAT = flat_material("mouth_mask", (0.02, 0.005, 0.005))
MOUTH_CAVITY_MAT = flat_material("mouth_cavity", (0.16, 0.025, 0.02), 0.8)
MOUTH_TONGUE_MAT = flat_material("mouth_tongue", (0.75, 0.22, 0.25), 0.45)
MOUTH_TEETH_MAT = flat_material("mouth_teeth", (0.92, 0.9, 0.82), 0.35)

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

def conformal_patch(xc, zc, half_w, half_h, nx, nz, inset, weights, uv_of, y_clamp=0.05, mat_index=None):
    """Elliptical grid of verts projected onto the surface from the front (-y) and
    pushed forward by `inset`. Hits are clamped to within y_clamp of the centre
    hit so rays that miss the feature's shell don't drag verts onto the body."""
    if mat_index is None:
        mat_index = ARM_MAT_INDEX
    c_hit = bvh.ray_cast(Vector((xc, -2.0, zc)), Vector((0, 1, 0)), 3.0)[0]
    y_c = c_hit.y if c_hit is not None else -0.30
    grid = []
    for j in range(nz):
        u = math.cos(math.pi * (j + 0.5) / nz)   # 1 = top .. -1 = bottom, clustered at the ends
        t = (1 - u) / 2
        zz = zc + half_h * u
        hw = half_w * math.sqrt(max(0.0, 1 - u * u))
        row = []
        for i in range(nx):
            s = i / (nx - 1)
            xx = xc + hw * (2 * s - 1)
            loc, _n, _f, _d = bvh.ray_cast(Vector((xx, -2.0, zz)), Vector((0, 1, 0)), 3.0)
            yy = loc.y if loc is not None else y_c
            yy = max(y_c - y_clamp, min(y_c + y_clamp, yy)) - inset
            v = bm.verts.new(Vector((xx, yy, zz)))
            new_vert_weights[v] = weights
            row.append((v, s, t))
        grid.append(row)
    for j in range(nz - 1):
        for i in range(nx - 1):
            quad = (grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i])
            try:
                f = bm.faces.new(tuple(q[0] for q in quad))
            except ValueError:
                continue
            f.material_index = mat_index
            f.smooth = True
            for l, (_v, s, t) in zip(f.loops, quad):
                l[uv_layer].uv = uv_of(s, t)
    return grid, y_c - inset

# ---------------------------------------------------------------- eyelid patches
# The eyes are painted on the dome, so blinking needs geometry: a conformal
# "sticker" over each eye, weighted to a Lid bone that points down the eye.
# JS keeps the bone's scale.y tiny (lid retracted under the brow) and raises
# it towards 1 to blink; the patch is modelled fully closed.
lid_bones = {}

def build_lid(side):
    x0, x1, z_top, z_bot = EYE[side]
    xc, zc = (x0 + x1) / 2, (z_top + z_bot) / 2
    # fur colour sampled beside the eye (the patch must look like skin, not eye)
    fur = []
    for sx in (x0 - 0.06, x1 + 0.06):
        loc, _n, fidx, _d = bvh.ray_cast(Vector((sx, -2.0, zc)), Vector((0, 1, 0)), 3.0)
        if loc is not None:
            fur.append(colour_at_hit(loc, fidx))
    fur = sum(fur, Vector()) / len(fur)
    for col_row, shade in ((LID_ROW[side], 1.0), (LID_ROW[side] + 1, 0.85)):
        for x in range(ARM_TEX_W):
            put_texel(x, col_row, fur * shade)
    conformal_patch(xc, zc, (x1 - x0) / 2 * 1.08, (z_top - z_bot) / 2 * 1.06, LID_NX, LID_NZ, LID_INSET,
                    {f"Lid.{side}": 1.0},
                    lambda s, t: (0.25, (LID_ROW[side] + 0.5 + t) / ARM_TEX_H), y_clamp=0.08)
    y_top = bvh.ray_cast(Vector((xc, -2.0, z_top)), Vector((0, 1, 0)), 3.0)[0]
    y_top = (y_top.y if y_top is not None else -0.30) - LID_INSET
    lid_bones[side] = (Vector((xc, y_top, z_top)), Vector((xc, y_top, z_bot)))

build_lid("L")
build_lid("R")

# ---------------------------------------------------------------- mouth
# The mouth is a stencil portal (set up in avatar.js): the *mask* is a flat
# ellipse on the lip line, scaled open by the Mouth bone; wherever the mask is
# visible the JS draws the *cavity* (a dark bowl recessed into the head), the
# tongue and the teeth instead of the muzzle. Those interior parts ride with the
# Head and are modelled at full-open size.
mouth_zc = MOUTH_C.z - MOUTH_H + 0.01

mouth_grid, mouth_y = conformal_patch(
    MOUTH_C.x, mouth_zc, MOUTH_W, MOUTH_H, MOUTH_NX, MOUTH_NZ, MOUTH_INSET,
    {"Mouth": 1.0}, lambda s, t: (0.5, 0.5), y_clamp=0.04, mat_index=MOUTH_MASK_MAT)
mouth_bone = (Vector((MOUTH_C.x, mouth_y, mouth_zc + MOUTH_H)),
              Vector((MOUTH_C.x, mouth_y, mouth_zc - MOUTH_H)))

def add_solid(verts_faces, mat_index, weights):
    vs = [bm.verts.new(p) for p in verts_faces[0]]
    for v in vs:
        new_vert_weights[v] = weights
    for idx in verts_faces[1]:
        try:
            f = bm.faces.new([vs[i] for i in idx])
        except ValueError:
            continue
        f.material_index = mat_index
        f.smooth = True
        for l in f.loops:
            l[uv_layer].uv = (0.5, 0.5)
    return vs

def ellipsoid(centre, rx, ry, rz, nu=16, nv=8, half=False):
    """UV ellipsoid around `centre`; half=True keeps only the +y half (a bowl
    opening towards -y, i.e. towards the camera) with its rim in the y=0 plane."""
    pts, faces = [], []
    rows = []
    for j in range(nv + 1):
        phi = math.pi * j / nv
        if half:
            phi = math.pi / 2 * j / nv        # equator (rim) .. pole (back wall)
        row = []
        for i in range(nu):
            th = 2 * math.pi * i / nu
            p = Vector((math.sin(phi) * math.cos(th) * rx, math.cos(phi) * ry, math.sin(phi) * math.sin(th) * rz))
            if half:
                p = Vector((math.cos(phi) * math.cos(th) * rx, math.sin(phi) * ry, math.cos(phi) * math.sin(th) * rz))
            pts.append(centre + p)
            row.append(len(pts) - 1)
        rows.append(row)
    for j in range(nv):
        for i in range(nu):
            a, b = rows[j][i], rows[j][(i + 1) % nu]
            c, d = rows[j + 1][(i + 1) % nu], rows[j + 1][i]
            faces.append((a, b, c, d))
    return pts, faces

# cavity: bowl behind the lip, rim just behind the mask, depth into the head (+y)
MOUTH_DEPTH = 0.11
cav_c = Vector((MOUTH_C.x, mouth_y + MOUTH_INSET + 0.002, mouth_zc))
add_solid(ellipsoid(cav_c, MOUTH_W * 1.15, MOUTH_DEPTH, MOUTH_H * 1.25, 18, 8, half=True),
          MOUTH_CAVITY_MAT, {"Head": 1.0})

# tongue: flattened ellipsoid resting on the cavity floor, tip a little forward
tongue_c = Vector((MOUTH_C.x, cav_c.y + MOUTH_DEPTH * 0.45, mouth_zc - MOUTH_H * 0.55))
tongue = ellipsoid(tongue_c, MOUTH_W * 0.62, MOUTH_DEPTH * 0.42, MOUTH_H * 0.42, 14, 7)
add_solid(tongue, MOUTH_TONGUE_MAT, {"Head": 1.0})

# teeth: small blocks hanging from the upper rim, just inside the cavity
tooth_w, tooth_h, tooth_d = MOUTH_W * 0.28, MOUTH_H * 0.42, 0.02
for k in (-1.55, -0.5, 0.5, 1.55):
    cx = MOUTH_C.x + k * tooth_w * 1.05
    x0, x1 = cx - tooth_w / 2, cx + tooth_w / 2
    y0, y1 = cav_c.y + 0.004, cav_c.y + 0.004 + tooth_d
    # start below the closed-mouth sliver (mask scale.y 0.05) so a shut mouth is just a dark line
    z1 = mouth_zc + MOUTH_H * 0.98 - 2 * MOUTH_H * 0.09
    z0 = z1 - tooth_h
    box = ([Vector((x0, y0, z0)), Vector((x1, y0, z0)), Vector((x1, y1, z0)), Vector((x0, y1, z0)),
            Vector((x0, y0, z1)), Vector((x1, y0, z1)), Vector((x1, y1, z1)), Vector((x0, y1, z1))],
           [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)])
    add_solid(box, MOUTH_TEETH_MAT, {"Head": 1.0})

bm.verts.index_update()
bmesh.ops.recalc_face_normals(bm, faces=[f for f in bm.faces if f.material_index >= ARM_MAT_INDEX])
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
bone_names = ["Torso", "Head", "UpperArm.L", "ForeArm.L", "Hand.L", "UpperArm.R", "ForeArm.R", "Hand.R",
              "Ear.L", "Ear.R", "Brow.L", "Brow.R", "Lid.L", "Lid.R", "Mouth"]
vgs = {n: mesh_ob.vertex_groups.new(name=n) for n in bone_names}

feature_of = {}
for name, idxs in feature_idx.items():
    for i in idxs:
        feature_of[i] = name

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
    if i in feature_of and not feature_of[i].startswith("Ear"):
        vgs[feature_of[i]].add([i], 1.0, "REPLACE")
        continue
    if p.z > Z_NECK + BLEND:
        w_l, w_r = ear_weight(p)
        w_ear = max(w_l, w_r)
        if w_ear > 1e-3:
            vgs["Ear.L" if w_l >= w_r else "Ear.R"].add([i], w_ear, "REPLACE")
            if 1 - w_ear > 1e-3:
                vgs["Head"].add([i], 1 - w_ear, "REPLACE")
            continue
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

# Face bones, all children of Head. Lid/Brow/Mouth bones point straight down
# (-Z) so their glTF local axes line up with world axes for simple JS control:
# scale.y = along the bone, position offsets in Head space.
bone("Ear.R", EAR_R_PIVOT, EAR_R_TIP, "Head")
bone("Ear.L", EAR_L_PIVOT, EAR_L_TIP, "Head")
for side in ("L", "R"):
    h, t = lid_bones[side]
    bone(f"Lid.{side}", h, t, "Head")
brow_c = {"R": Vector((-0.28, -0.30, 0.49)), "L": Vector((0.13, -0.29, 0.42))}
for side in ("L", "R"):
    c = brow_c[side]
    bone(f"Brow.{side}", c, c + Vector((0, 0, -0.1)), "Head")
bone("Mouth", mouth_bone[0], mouth_bone[1], "Head")

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
