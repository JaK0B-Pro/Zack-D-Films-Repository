"""Shared Blender helpers: scene setup, materials and reusable models."""
import bpy, bmesh, math, os
from mathutils import Vector

FPS = 24
RES = (540, 960)


def reset(frames, samples=16):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.render.engine = 'CYCLES'
    s.cycles.device = 'CPU'
    s.cycles.samples = samples
    s.cycles.use_adaptive_sampling = True
    s.cycles.adaptive_threshold = 0.05
    s.cycles.use_denoising = True
    s.cycles.denoising_prefilter = 'FAST'
    s.cycles.max_bounces = 4
    s.cycles.transparent_max_bounces = 8
    s.cycles.glossy_bounces = 2
    s.cycles.diffuse_bounces = 2
    s.cycles.transmission_bounces = 4
    s.render.use_persistent_data = True
    s.render.resolution_x, s.render.resolution_y = RES
    s.render.fps = FPS
    s.frame_start, s.frame_end = 1, frames
    s.view_settings.view_transform = 'AgX'
    s.view_settings.look = 'AgX - Medium High Contrast'
    s.render.image_settings.file_format = 'PNG'
    w = bpy.data.worlds.new("W")
    s.world = w
    w.use_nodes = True
    world_color((0.01, 0.01, 0.012), 1.0)
    return s


def world_color(col, strength=1.0):
    bg = bpy.context.scene.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (*col, 1)
    bg.inputs[1].default_value = strength


def mat(name, color, rough=0.5, metal=0.0, sss=0.0, coat=0.0, emit=None, emit_strength=0.0, alpha=1.0, transmission=0.0, ior=1.45):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    p.inputs["Subsurface Weight"].default_value = sss
    p.inputs["Subsurface Radius"].default_value = (0.9, 0.25, 0.12)
    p.inputs["Subsurface Scale"].default_value = 0.05
    p.inputs["Coat Weight"].default_value = coat
    p.inputs["Alpha"].default_value = alpha
    p.inputs["Transmission Weight"].default_value = transmission
    p.inputs["IOR"].default_value = ior
    if emit:
        p.inputs["Emission Color"].default_value = (*emit, 1)
        p.inputs["Emission Strength"].default_value = emit_strength
    return m


def node(m, kind, loc=(0, 0)):
    n = m.node_tree.nodes.new(kind)
    n.location = loc
    return n


def link(m, a, b):
    m.node_tree.links.new(a, b)


def bsdf(m):
    return m.node_tree.nodes["Principled BSDF"]


def emission_mat(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs[0].default_value = (*color, 1)
    e.inputs[1].default_value = strength
    nt.links.new(e.outputs[0], out.inputs[0])
    return m


def xray_mat(name, color, strength=3.0, power=0.35):
    """Glowing edge 'X-ray' look: emission weighted by facing, added over transparency."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs[0].default_value = power
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs[0].default_value = (*color, 1)
    e.inputs[1].default_value = strength
    t = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lw.outputs["Facing"], mix.inputs[0])
    nt.links.new(t.outputs[0], mix.inputs[1])
    nt.links.new(e.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    return m


# ---------- standard materials ----------

def skin_mat():
    m = mat("Skin", (0.78, 0.5, 0.38), rough=0.45, sss=0.35)
    tc = node(m, "ShaderNodeTexCoord", (-800, 0))
    n = node(m, "ShaderNodeTexNoise", (-600, 0))
    link(m, tc.outputs["Object"], n.inputs["Vector"])
    n.inputs["Scale"].default_value = 25
    n.inputs["Detail"].default_value = 8
    b = node(m, "ShaderNodeBump", (-300, -200))
    b.inputs["Strength"].default_value = 0.08
    link(m, n.outputs["Fac"], b.inputs["Height"])
    link(m, b.outputs["Normal"], bsdf(m).inputs["Normal"])
    return m


def muscle_mat(name="Muscle"):
    """Wet red muscle with fibre striations along the object's Y axis and bundle cells."""
    m = mat(name, (0.42, 0.03, 0.03), rough=0.3, sss=0.25, coat=0.35)
    tc = node(m, "ShaderNodeTexCoord", (-1100, 0))
    wave = node(m, "ShaderNodeTexWave", (-800, 100))
    wave.wave_type = 'BANDS'
    wave.bands_direction = 'Z'
    wave.inputs["Scale"].default_value = 18
    wave.inputs["Distortion"].default_value = 6
    wave.inputs["Detail"].default_value = 4
    vor = node(m, "ShaderNodeTexVoronoi", (-800, -200))
    vor.feature = 'DISTANCE_TO_EDGE'
    vor.inputs["Scale"].default_value = 7
    link(m, tc.outputs["Object"], wave.inputs["Vector"])
    link(m, tc.outputs["Object"], vor.inputs["Vector"])
    edge = node(m, "ShaderNodeMapRange", (-550, -200))
    edge.inputs["From Min"].default_value = 0.0
    edge.inputs["From Max"].default_value = 0.06
    link(m, vor.outputs["Distance"], edge.inputs["Value"])
    ramp = node(m, "ShaderNodeValToRGB", (-550, 150))
    ramp.color_ramp.elements[0].color = (0.22, 0.01, 0.015, 1)
    ramp.color_ramp.elements[1].color = (0.55, 0.06, 0.05, 1)
    link(m, wave.outputs["Fac"], ramp.inputs["Fac"])
    mixc = node(m, "ShaderNodeMix", (-250, 100))
    mixc.data_type = 'RGBA'
    mixc.inputs["B"].default_value = (0.85, 0.65, 0.55, 1)  # pale connective tissue between bundles
    inv = node(m, "ShaderNodeMath", (-350, -200))
    inv.operation = 'SUBTRACT'
    inv.inputs[0].default_value = 1.0
    link(m, edge.outputs["Result"], inv.inputs[1])
    link(m, inv.outputs[0], mixc.inputs["Factor"])
    link(m, ramp.outputs["Color"], mixc.inputs["A"])
    link(m, mixc.outputs["Result"], bsdf(m).inputs["Base Color"])
    bump = node(m, "ShaderNodeBump", (-250, -300))
    bump.inputs["Strength"].default_value = 0.25
    link(m, wave.outputs["Fac"], bump.inputs["Height"])
    link(m, bump.outputs["Normal"], bsdf(m).inputs["Normal"])
    return m


def fat_mat():
    m = mat("Fat", (0.92, 0.72, 0.32), rough=0.35, sss=0.3, coat=0.2)
    vor = node(m, "ShaderNodeTexVoronoi", (-600, 0))
    vor.inputs["Scale"].default_value = 40
    b = node(m, "ShaderNodeBump", (-300, -200))
    b.inputs["Strength"].default_value = 0.3
    link(m, vor.outputs["Distance"], b.inputs["Height"])
    link(m, b.outputs["Normal"], bsdf(m).inputs["Normal"])
    return m


def bone_mat():
    m = mat("Bone", (0.88, 0.84, 0.72), rough=0.55, sss=0.1)
    n = node(m, "ShaderNodeTexNoise", (-600, 0))
    n.inputs["Scale"].default_value = 25
    b = node(m, "ShaderNodeBump", (-300, -200))
    b.inputs["Strength"].default_value = 0.15
    link(m, n.outputs["Fac"], b.inputs["Height"])
    link(m, b.outputs["Normal"], bsdf(m).inputs["Normal"])
    return m


def copper_mat():
    return mat("Copper", (0.95, 0.5, 0.3), rough=0.22, metal=1.0)


def blood_mat():
    return mat("Blood", (0.18, 0.0, 0.005), rough=0.08, coat=0.6, sss=0.2)


def wound_mat():
    return mat("Damaged", (0.12, 0.005, 0.005), rough=0.25, coat=0.5)


# ---------- objects ----------

def lathe(name, profile, segs=64):
    """Revolve a list of (radius, z) points around Z."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        ring = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
        rings.append(ring)
    for k in range(len(rings) - 1):
        for i in range(segs):
            j = (i + 1) % segs
            bm.faces.new((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def bullet(name="Bullet", scale=1.0):
    """9mm-style round-nose jacketed bullet, pointing along +Z, base at z=0."""
    prof = [(0.0, 0.0), (0.42, 0.0), (0.45, 0.03), (0.45, 0.55)]
    for i in range(1, 13):
        a = (math.pi / 2) * i / 12
        prof.append((0.45 * math.cos(a), 0.55 + 0.55 * math.sin(a)))
    ob = lathe(name, prof)
    ob.data.materials.append(copper_mat())
    ob.scale = (scale, scale, scale)
    return ob


def area_light(loc, target, energy, size=2.0, color=(1, 1, 1)):
    ld = bpy.data.lights.new("L", 'AREA')
    ld.energy = energy
    ld.size = size
    ld.color = color
    ob = bpy.data.objects.new("L", ld)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    look_at(ob, target)
    return ob


def point_light(loc, energy, color=(1, 1, 1), radius=0.2):
    ld = bpy.data.lights.new("P", 'POINT')
    ld.energy = energy
    ld.color = color
    ld.shadow_soft_size = radius
    ob = bpy.data.objects.new("P", ld)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    return ob


def look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def camera(loc, target, lens=50, dof_target=None, fstop=2.8):
    cd = bpy.data.cameras.new("Cam")
    cd.lens = lens
    ob = bpy.data.objects.new("Cam", cd)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    look_at(ob, target)
    bpy.context.scene.camera = ob
    if dof_target is not None:
        cd.dof.use_dof = True
        cd.dof.focus_object = dof_target
        cd.dof.aperture_fstop = fstop
    return ob


def key(ob, frame, **props):
    for k, v in props.items():
        setattr(ob, k, v)
        ob.keyframe_insert(data_path=k, frame=frame)


def ease_all(ob, mode='BEZIER'):
    ad = ob.animation_data
    if ad and ad.action:
        for fc in fcurves(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = mode


def fcurves(action):
    """Blender 5 stores fcurves in layered action channelbags."""
    if hasattr(action, "fcurves") and len(getattr(action, "fcurves", [])):
        return list(action.fcurves)
    out = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for cb in strip.channelbags:
                out.extend(cb.fcurves)
    return out


def cam_shake(cam, f0, f1, amp=0.05, seed=0):
    import random
    rnd = random.Random(seed)
    base = cam.location.copy()
    for f in range(f0, f1 + 1):
        k = 1 - (f - f0) / max(1, f1 - f0)
        cam.location = base + Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * amp * k
        cam.keyframe_insert("location", frame=f)
    cam.location = base
    cam.keyframe_insert("location", frame=f1 + 1)


def floor_backdrop(color=(0.02, 0.02, 0.025), z=-2):
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, z))
    p = bpy.context.object
    p.data.materials.append(mat("Floor", color, rough=0.6))
    return p


def render(outdir, frame=None):
    s = bpy.context.scene
    os.makedirs(outdir, exist_ok=True)
    if frame is not None:
        s.frame_set(frame)
        s.render.filepath = os.path.join(outdir, f"preview_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
    else:
        s.render.filepath = os.path.join(outdir, "")
        bpy.ops.render.render(animation=True)
