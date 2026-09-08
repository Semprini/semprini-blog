"""Strip the avatar's textures down to one flat material with a lit scene, and
(later, once sculpting is done) unwrap it and hand over a blank paint image.

Two stages, because an unwrap only survives if the geometry has stopped moving:

  stage 1 - sculpt        UNWRAP=none
      blender -b data/Semprini_rigged.blend --factory-startup \
          --python data/blender_scripts/setup_paint.py -- data/Semprini_sculpt.blend "" 2048 none
      Textures gone, bust and limbs merged into one flat "fur" material, lights
      set up, lids and mouth posed as the site shows them. Sculpt in here.

  stage 2 - paint         UNWRAP=A (or B)
      blender -b data/Semprini_sculpt.blend --factory-startup \
          --python data/blender_scripts/setup_paint.py -- data/Semprini_paint.blend data/semprini_paint.png 2048 A
      Adds a non-overlapping UV layout and a blank 2048 image, and leaves the
      object in Texture Paint mode.

Why the unwrap is needed at all: the bust and the generated arms/body/legs were
unwrapped into the same UV layer against two different images, so 47% of the
used UV space had two different parts of the model stacked on it - painting one
repainted the other somewhere else entirely. Both modes below fix that outright:

  A  keeps each existing island's shape, evens the texel density across bust and
     limbs, and repacks so nothing overlaps. Measured on the pre-sculpt mesh
     this gave 155 islands over 62% of the sheet.
  B  re-cuts everything with Smart UV Project: 370 islands over 51%. Use this if
     sculpting has stretched the bust's original islands out of shape.

Mode A needs to know which faces are the generated limbs, so stage 1 records
that in a "limb" face attribute that survives sculpting (but not a remesh).

These files are terminal: build_avatar.py regenerates Semprini_rigged.blend from
data/Semprini.blend and would discard anything sculpted or unwrapped here.

Coordinates (Blender, Z up, character faces -Y).
"""
import sys, os, math
import bpy, bmesh
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT_BLEND = argv[0] if len(argv) > 0 else "data/Semprini_sculpt.blend"
OUT_PNG = argv[1] if len(argv) > 1 else ""
RES = int(argv[2]) if len(argv) > 2 else 2048
UNWRAP = (argv[3] if len(argv) > 3 else "none").upper()
PAINT = UNWRAP in ("A", "B")

FUR_MATS = ("mat0", "mat_arms")          # merged into the one paintable material
KEEP_MATS = ("mouth_mask", "mouth_cavity", "mouth_tongue", "mouth_teeth")
DROP_IMAGES = ("texture", "texture.001", "texture.002", "semprini_arms")
BASE_TONE = 0.216        # linear; = sRGB 128, a neutral mid grey to judge form and values against
PACK_MARGIN = 0.004      # ~8 px gutter at 2048, so strokes cannot bleed island to island
ANGLE_LIMIT = math.radians(66)
LIMB_ATTR = "limb"

scene = bpy.context.scene
ob = bpy.data.objects["SempriniAvatar"]
rig = bpy.data.objects["SempriniRig"]
me = ob.data
bpy.ops.object.select_all(action="DESELECT")
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode="OBJECT")

# ---------------------------------------------------------------- one fur material
# Idempotent: stage 2 runs against a file that has already been through stage 1.
fur = bpy.data.materials.get("fur")
first_pass = fur is None
if first_pass:
    fur = bpy.data.materials.new("fur")
    fur.use_nodes = True
    nt = fur.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (420, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (110, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (BASE_TONE, BASE_TONE, BASE_TONE, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.65   # a little sheen reads form better than pure matte
    bsdf.inputs["Metallic"].default_value = 0.0

    # Remember which faces are the generated arms/body/legs before the slots go,
    # so a later unwrap can still re-cut only those and leave the bust alone.
    name_of = [m.name if m else "" for m in me.materials]
    limb = {p.index for p in me.polygons if name_of[p.material_index] == "mat_arms"}
    attr = me.attributes.new(LIMB_ATTR, "BOOLEAN", "FACE")
    attr.data.foreach_set("value", [p.index in limb for p in me.polygons])

    new_mats = [fur] + [bpy.data.materials[n] for n in KEEP_MATS if n in bpy.data.materials]
    remap = {i: (0 if n in FUR_MATS else next((j for j, m in enumerate(new_mats) if m.name == n), 0))
             for i, n in enumerate(name_of)}
    indices = [remap[p.material_index] for p in me.polygons]
    me.materials.clear()
    for m in new_mats:
        me.materials.append(m)
    for p, i in zip(me.polygons, indices):
        p.material_index = i

    for n in DROP_IMAGES:
        old = bpy.data.images.get(n)
        if old:
            bpy.data.images.remove(old)
            print("removed image", n)
    for n in FUR_MATS:
        old = bpy.data.materials.get(n)
        if old and old.users == 0:
            bpy.data.materials.remove(old)

ob.active_material_index = 0
print("materials:", [m.name for m in me.materials])

# ---------------------------------------------------------------- unwrap + paint image
if PAINT:
    img = bpy.data.images.new("semprini_paint", RES, RES, alpha=False)
    img.generated_color = (BASE_TONE, BASE_TONE, BASE_TONE, 1.0)
    img.filepath_raw = bpy.path.abspath(
        "//" + os.path.relpath(OUT_PNG, os.path.dirname(OUT_BLEND) or "."))
    img.file_format = "PNG"
    img.save()
    # Re-point at the file on disk so painting edits a real PNG rather than a
    # generated buffer that only exists inside the .blend.
    img.source = "FILE"
    img.filepath = "//" + os.path.basename(OUT_PNG)
    img.reload()
    img.colorspace_settings.name = "sRGB"

    nt = fur.node_tree
    tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None) or nt.nodes.new("ShaderNodeTexImage")
    tex.location = (-260, 0)
    tex.image = img
    tex.interpolation = "Linear"
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 1.0
    nt.nodes.active = tex        # Texture Paint in MATERIAL mode paints the active image node
    print("image", img.filepath, img.size[:])

    attr = me.attributes.get(LIMB_ATTR)
    limb = set()
    if attr:
        vals = [False] * len(me.polygons)
        attr.data.foreach_get("value", vals)
        limb = {i for i, v in enumerate(vals) if v}

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="FACE")

    def select(pred):
        bpy.ops.mesh.select_all(action="DESELECT")
        bm = bmesh.from_edit_mesh(me)
        bm.faces.ensure_lookup_table()
        for f in bm.faces:
            f.select = pred(f)
        bmesh.update_edit_mesh(me)
        return sum(1 for f in bm.faces if f.select)

    if UNWRAP == "A" and limb:
        # Only the limbs need re-cutting: their original UVs were a texel-row
        # strip, one row per ring, which is unusable as an island.
        n = select(lambda f: f.index in limb)
        bpy.ops.uv.smart_project(angle_limit=ANGLE_LIMIT, island_margin=0.0,
                                 correct_aspect=True, scale_to_bounds=False)
        print(f"smart-projected {n} limb faces")
        select(lambda f: f.material_index == 0)
        bpy.ops.uv.average_islands_scale()      # one texel density over bust and limbs
    else:
        n = select(lambda f: f.material_index == 0)
        bpy.ops.uv.smart_project(angle_limit=ANGLE_LIMIT, island_margin=0.0,
                                 correct_aspect=True, scale_to_bounds=False)
        print(f"smart-projected all {n} fur faces")

    select(lambda f: f.material_index == 0)
    bpy.ops.uv.pack_islands(margin=PACK_MARGIN, rotate=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    me.uv_layers.active = me.uv_layers[0]

# ---------------------------------------------------------------- lighting
if not bpy.data.collections.get("Lighting"):
    lights = bpy.data.collections.new("Lighting")
    scene.collection.children.link(lights)

    def add_light(name, loc, aim, energy, size, colour=(1.0, 1.0, 1.0)):
        d = bpy.data.lights.new(name, "AREA")
        d.energy = energy
        d.size = size
        d.color = colour
        o = bpy.data.objects.new(name, d)
        lights.objects.link(o)
        o.location = Vector(loc)
        o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        return o

    # The character faces -Y, so the key sits front-left-high and the rim behind it.
    # Levelled so the neutral BASE_TONE surface renders back as a mid grey under
    # the Standard view transform, rather than clipping to white.
    add_light("Key",    (-2.6, -3.2,  2.4), (-0.1, -0.2, -0.3), 320, 4.0)
    add_light("Fill",   ( 3.0, -2.6,  0.2), (-0.1, -0.2, -0.8), 110, 4.0, (0.96, 0.97, 1.0))
    add_light("Rim",    ( 1.2,  2.8,  2.2), (-0.1, -0.2,  0.0), 220, 3.0)
    add_light("Bounce", ( 0.0, -1.6, -3.2), (-0.1, -0.3, -1.4),  70, 4.0, (1.0, 0.98, 0.94))

world = scene.world or bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
if bg:
    bg.inputs["Color"].default_value = (0.05, 0.05, 0.055, 1.0)
    bg.inputs["Strength"].default_value = 1.0

for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
    try:
        scene.render.engine = eng
        break
    except TypeError:
        continue
scene.view_settings.view_transform = "Standard"   # see the colour you actually picked
print("engine", scene.render.engine)

# ---------------------------------------------------------------- pose to match the site
# avatar.js retracts the lid patches and shuts the mouth mask at rest. Left at
# their rest size they sit right over the eyes and lips, hiding both.
for side in ("L", "R"):
    rig.pose.bones[f"Lid.{side}"].scale.y = 0.06
rig.pose.bones["Mouth"].scale = (0.4, 0.05, 1.0)

# ---------------------------------------------------------------- tool + viewport
ts = scene.tool_settings
ip = ts.image_paint
ip.mode = "MATERIAL"                 # paint into the material's active image node
ip.seam_bleed = 4                    # px painted past each island edge
ip.use_occlude = True                # brows, ears and lids are shells sitting on the dome:
ip.use_backface_culling = True       # don't paint through them onto what is behind
ip.normal_angle = 80
ip.use_normal_falloff = True

for ws in bpy.data.workspaces:
    for screen in ws.screens:
        for area in screen.areas:
            for sp in area.spaces:
                if sp.type == "VIEW_3D":
                    if ws.name in ("Sculpting", "Texture Paint"):
                        # flat shading: read form and texture colour without
                        # lighting skewing what you sculpt or mix
                        sp.shading.type = "SOLID"
                        sp.shading.color_type = "TEXTURE" if PAINT else "MATERIAL"
                        sp.shading.light = "MATCAP" if ws.name == "Sculpting" else "FLAT"
                    else:
                        sp.shading.type = "MATERIAL"
                        sp.shading.use_scene_lights = True
                        sp.shading.use_scene_world = True
                elif sp.type == "IMAGE_EDITOR" and PAINT:
                    sp.image = img

try:
    bpy.ops.object.mode_set(mode="TEXTURE_PAINT" if PAINT else "SCULPT")
    print("mode", ob.mode, "brush", getattr(ip.brush if PAINT else ts.sculpt.brush, "name", None))
except RuntimeError as e:
    print("could not enter mode headless:", e)

bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print("SAVED", OUT_BLEND, "| stage:", "paint (unwrap " + UNWRAP + ")" if PAINT else "sculpt (no unwrap)")
