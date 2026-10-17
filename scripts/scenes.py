"""Builds and renders each shot of the short.

Usage (bpy as a Python module):
    python3 scripts/scenes.py <scene_id> [preview_frame]
"""
import bpy, math, random, json, os, sys
from mathutils import Vector

sys.path.insert(0, os.path.dirname(__file__))
import blib as B

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMING = {t["id"]: t for t in json.load(open(os.path.join(ROOT, "audio", "timing.json")))}
PAD = 0.45  # seconds of breathing room after each line


def nframes(sid):
    return round((TIMING[sid]["dur"] + PAD) * B.FPS)


def rad(d):
    return math.radians(d)


# ------------------------------------------------------------------ shared pieces

def dust(count, bounds, size=0.01, color=(1, 0.85, 0.7), strength=4, seed=1):
    rnd = random.Random(seed)
    m = B.emission_mat("Dust", color, strength)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=size)
    proto = bpy.context.object
    proto.data.materials.append(m)
    obs = [proto]
    (x0, x1), (y0, y1), (z0, z1) = bounds
    proto.location = (rnd.uniform(x0, x1), rnd.uniform(y0, y1), rnd.uniform(z0, z1))
    for _ in range(count - 1):
        o = proto.copy()
        bpy.context.collection.objects.link(o)
        o.location = (rnd.uniform(x0, x1), rnd.uniform(y0, y1), rnd.uniform(z0, z1))
        s = rnd.uniform(0.4, 1.4)
        o.scale = (s, s, s)
        obs.append(o)
    return obs


def denim_mat():
    m = B.mat("Denim", (0.06, 0.1, 0.2), rough=0.8)
    w = B.node(m, "ShaderNodeTexWave", (-600, 0))
    w.inputs["Scale"].default_value = 300
    w.inputs["Distortion"].default_value = 2
    b = B.node(m, "ShaderNodeBump", (-300, -200))
    b.inputs["Strength"].default_value = 0.2
    B.link(m, w.outputs["Fac"], b.inputs["Height"])
    B.link(m, b.outputs["Normal"], B.bsdf(m).inputs["Normal"])
    return m


def cylinder(name, r, depth, loc=(0, 0, 0), rot=(0, 0, 0), verts=128, material=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    bpy.ops.object.shade_smooth()
    if material:
        o.data.materials.append(material)
    return o


def boolean(target, cutter, solver='EXACT'):
    mod = target.modifiers.new("Bool", 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.object = cutter
    mod.solver = solver
    if solver == 'EXACT':
        mod.material_mode = 'TRANSFER'
    return mod


def thigh_section(artery=True):
    """Thigh cut open across its length: camera sees the cut face at y=0, limb extends to +y."""
    L = 5.0
    rot = (rad(90), 0, 0)
    layers = []
    skin = cylinder("Skin", 1.0, L, (0, L / 2, 0), rot, material=B.skin_mat())
    fat = cylinder("Fat", 0.95, L, (0, L / 2 - 0.004, 0), rot, material=B.fat_mat())
    muscle = cylinder("Muscle", 0.82, L, (0, L / 2 - 0.008, 0), rot, material=B.muscle_mat())
    bone = cylinder("Bone", 0.2, L, (0, L / 2 - 0.014, -0.05), rot, material=B.bone_mat())
    marrow = cylinder("Marrow", 0.11, L, (0, L / 2 - 0.018, -0.05), rot,
                      material=B.mat("Marrow", (0.55, 0.12, 0.05), rough=0.6, sss=0.3))
    layers = [skin, fat, muscle]
    extra = [bone, marrow]
    if artery:
        art = cylinder("Artery", 0.075, L, (0.32, L / 2 - 0.02, -0.38), rot, verts=48,
                       material=B.mat("ArteryWall", (0.75, 0.25, 0.22), rough=0.3, coat=0.5))
        lum = cylinder("Lumen", 0.05, L, (0.32, L / 2 - 0.024, -0.38), rot, verts=48, material=B.blood_mat())
        vein = cylinder("Vein", 0.085, L, (0.48, L / 2 - 0.02, -0.28), rot, verts=48,
                        material=B.mat("Vein", (0.12, 0.08, 0.3), rough=0.3, coat=0.5))
        nerve = cylinder("Nerve", 0.045, L, (0.2, L / 2 - 0.02, -0.48), rot, verts=32,
                         material=B.mat("Nerve", (0.95, 0.88, 0.5), rough=0.4))
        extra += [art, lum, vein, nerve]
    # the cut face reads better with a slightly rounded far end hidden from view
    return layers, extra


def tunnel_cutter(z, x_start=-1.4, r=0.075):
    """Cylinder along +X whose left end sits at x_start; scale.x = tunnel length."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=r, depth=1.0, rotation=(0, rad(90), 0))
    c = bpy.context.object
    bpy.ops.object.transform_apply(rotation=True)
    for v in c.data.vertices:
        v.co.x += 0.5
    c.location = (x_start, 0, z)
    c.name = "TunnelCutter"
    c.data.materials.append(B.wound_mat())
    c.hide_render = True
    c.display_type = 'WIRE'
    return c


def sphere(name, r, loc, scale=(1, 1, 1), material=None, segs=64, rings=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=rings, radius=r, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.shade_smooth()
    if material:
        o.data.materials.append(material)
    return o


def tube(name, pts, r, material, parent=None):
    cd = bpy.data.curves.new(name, 'CURVE')
    cd.dimensions = '3D'
    cd.bevel_depth = r
    cd.bevel_resolution = 6
    cd.use_fill_caps = True
    sp = cd.splines.new('BEZIER')
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    o = bpy.data.objects.new(name, cd)
    bpy.context.collection.objects.link(o)
    cd.materials.append(material)
    if parent:
        o.parent = parent
    return o


def organic(o, strength=0.06, size=0.6, levels=2):
    sub = o.modifiers.new("Sub", 'SUBSURF')
    sub.levels = sub.render_levels = levels
    tex = bpy.data.textures.new(o.name + "Tex", 'CLOUDS')
    tex.noise_scale = size
    d = o.modifiers.new("Disp", 'DISPLACE')
    d.texture = tex
    d.strength = strength
    d.mid_level = 0.5


def heart_mat():
    m = B.mat("HeartMuscle", (0.45, 0.06, 0.05), rough=0.3, sss=0.3, coat=0.5)
    tc = B.node(m, "ShaderNodeTexCoord", (-1000, 0))
    n = B.node(m, "ShaderNodeTexNoise", (-800, 0))
    n.inputs["Scale"].default_value = 2.2
    n.inputs["Detail"].default_value = 6
    n.inputs["Distortion"].default_value = 1.2
    B.link(m, tc.outputs["Object"], n.inputs["Vector"])
    ramp = B.node(m, "ShaderNodeValToRGB", (-500, 0))
    ramp.color_ramp.elements[0].position = 0.5
    ramp.color_ramp.elements[0].color = (0.42, 0.05, 0.04, 1)
    ramp.color_ramp.elements[1].position = 0.66
    ramp.color_ramp.elements[1].color = (0.85, 0.62, 0.28, 1)   # fat along coronary grooves
    B.link(m, n.outputs["Fac"], ramp.inputs["Fac"])
    B.link(m, ramp.outputs["Color"], B.bsdf(m).inputs["Base Color"])
    n2 = B.node(m, "ShaderNodeTexNoise", (-800, -300))
    n2.inputs["Scale"].default_value = 30
    b = B.node(m, "ShaderNodeBump", (-300, -250))
    b.inputs["Strength"].default_value = 0.15
    B.link(m, n2.outputs["Fac"], b.inputs["Height"])
    B.link(m, b.outputs["Normal"], B.bsdf(m).inputs["Normal"])
    return m


def heart_model(name="Heart"):
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    hm = heart_mat()
    aorta_m = B.mat("Aorta", (0.62, 0.09, 0.07), rough=0.3, coat=0.5, sss=0.2)
    pulm_m = B.mat("Pulm", (0.22, 0.12, 0.42), rough=0.3, coat=0.5, sss=0.2)
    v = sphere("Ventricles", 1.0, (0, 0, 0), (0.95, 0.8, 1.15), hm)
    t = v.modifiers.new("Taper", 'SIMPLE_DEFORM')
    t.deform_method = 'TAPER'
    t.deform_axis = 'Z'
    t.factor = 0.35
    organic(v, 0.08, 0.7)
    v.rotation_euler = (0, rad(-28), rad(10))
    ra = sphere("RA", 0.5, (-0.62, -0.05, 0.85), (1, 0.9, 1), hm)
    la = sphere("LA", 0.45, (0.55, 0.35, 0.95), (1, 0.9, 0.9), hm)
    for o in (ra, la):
        organic(o, 0.06, 0.5)
    parts = [v, ra, la,
             tube("Aorta", [(-0.05, 0.15, 0.7), (0.0, 0.15, 1.75), (-0.6, 0.35, 2.05), (-1.05, 0.45, 1.6), (-1.1, 0.5, 0.6)], 0.26, aorta_m),
             tube("Pulm", [(0.25, -0.35, 0.75), (0.4, -0.35, 1.45), (0.85, -0.1, 1.7), (1.3, 0.1, 1.6)], 0.22, pulm_m),
             tube("SVC", [(-0.7, 0.0, 1.1), (-0.7, 0.05, 2.1)], 0.2, pulm_m)]
    for i, (x, h) in enumerate(((-0.35, 2.6), (-0.65, 2.55), (-0.9, 2.4))):
        parts.append(tube(f"Branch{i}", [(x, 0.4, 1.9), (x - 0.05, 0.4, h)], 0.09, aorta_m))
    for o in parts:
        o.parent = root
    return root


def brain_object():
    m = bpy.data.materials.new("BrainTissue")
    m.use_nodes = True
    m.displacement_method = 'BOTH'
    p = B.bsdf(m)
    p.inputs["Roughness"].default_value = 0.35
    p.inputs["Subsurface Weight"].default_value = 0.35
    p.inputs["Subsurface Radius"].default_value = (0.9, 0.3, 0.2)
    p.inputs["Subsurface Scale"].default_value = 0.04
    p.inputs["Coat Weight"].default_value = 0.4
    tc = B.node(m, "ShaderNodeTexCoord", (-1100, 0))
    n = B.node(m, "ShaderNodeTexNoise", (-900, 0))
    n.inputs["Scale"].default_value = 2.6
    n.inputs["Detail"].default_value = 2
    n.inputs["Distortion"].default_value = 5
    B.link(m, tc.outputs["Object"], n.inputs["Vector"])
    mr = B.node(m, "ShaderNodeMapRange", (-650, 0))
    mr.inputs["From Min"].default_value = 0.47
    mr.inputs["From Max"].default_value = 0.53
    B.link(m, n.outputs["Fac"], mr.inputs["Value"])
    disp = B.node(m, "ShaderNodeDisplacement", (-200, -400))
    disp.inputs["Scale"].default_value = 0.07
    disp.inputs["Midlevel"].default_value = 0.5
    B.link(m, mr.outputs["Result"], disp.inputs["Height"])
    B.link(m, disp.outputs["Displacement"], m.node_tree.nodes["Material Output"].inputs["Displacement"])
    mix = B.node(m, "ShaderNodeMix", (-300, 200))
    mix.data_type = 'RGBA'
    mix.inputs["A"].default_value = (0.85, 0.45, 0.45, 1)
    mix.inputs["B"].default_value = (0.3, 0.32, 0.42, 1)
    crev = B.node(m, "ShaderNodeMix", (-150, 300))
    crev.data_type = 'RGBA'
    crev.blend_type = 'MULTIPLY'
    crev.inputs["Factor"].default_value = 1.0
    ramp = B.node(m, "ShaderNodeValToRGB", (-450, 400))
    ramp.color_ramp.elements[0].color = (0.35, 0.18, 0.2, 1)
    ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    B.link(m, mr.outputs["Result"], ramp.inputs["Fac"])
    B.link(m, mix.outputs["Result"], crev.inputs["A"])
    B.link(m, ramp.outputs["Color"], crev.inputs["B"])
    B.link(m, crev.outputs["Result"], p.inputs["Base Color"])
    root = bpy.data.objects.new("Brain", None)
    bpy.context.collection.objects.link(root)
    for x in (-0.5, 0.5):
        h = sphere("Hemi", 1.0, (x, 0, 0), (0.5, 1.0, 0.7), m)
        t = h.modifiers.new("Flat", 'SIMPLE_DEFORM')
        t.deform_method = 'TAPER'
        t.deform_axis = 'Y'
        t.factor = 0.15
        sub = h.modifiers.new("Sub", 'SUBSURF')
        sub.levels = sub.render_levels = 3
        h.parent = root
    c = sphere("Cerebellum", 1.0, (0, 0.7, -0.55), (0.75, 0.42, 0.35), m)
    sub = c.modifiers.new("Sub", 'SUBSURF')
    sub.levels = sub.render_levels = 2
    c.parent = root
    st = tube("Stem", [(0, 0.35, -0.4), (0, 0.45, -1.4)], 0.2, m)
    st.parent = root
    return root, mix


def rbc_proto():
    prof = [(0.0, 0.12), (0.3, 0.1), (0.62, 0.26), (0.88, 0.22), (1.0, 0.0),
            (0.88, -0.22), (0.62, -0.26), (0.3, -0.1), (0.0, -0.12)]
    o = B.lathe("RBC", prof, segs=24)
    o.data.materials.append(B.mat("RBC", (0.55, 0.02, 0.02), rough=0.3, sss=0.5, coat=0.3))
    return o


# ------------------------------------------------------------------ scenes

def scene_hook():
    F = nframes("hook")
    B.reset(F)
    B.world_color((0.012, 0.014, 0.02))
    b = B.bullet(scale=0.1)
    b.rotation_euler = (0, rad(90), 0)
    # bullet flies +X and spins about its axis
    B.key(b, 1, location=(-1.6, 0, 0))
    B.key(b, F, location=(3.2, 0, 0))
    B.ease_all(b, 'LINEAR')
    b.keyframe_insert("rotation_euler", frame=1)
    b.rotation_euler = (rad(720), rad(90), 0)
    b.keyframe_insert("rotation_euler", frame=F)
    B.ease_all(b, 'LINEAR')
    # the target: a thigh in jeans
    leg = cylinder("Leg", 0.9, 8, (5.0, 0.6, 0), material=denim_mat())
    # side-tracking camera that slowly swings in behind the bullet
    cam = B.camera((-1.2, -0.75, 0.12), (-1.6, 0, 0), lens=30, dof_target=b, fstop=2.0)
    tgt = bpy.data.objects.new("CamTarget", None)
    bpy.context.collection.objects.link(tgt)
    c = cam.constraints.new('TRACK_TO')
    c.target = tgt
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'
    B.key(tgt, 1, location=(-1.52, 0, 0))
    B.key(tgt, F, location=(3.35, 0, 0))
    B.ease_all(tgt, 'LINEAR')
    B.key(cam, 1, location=(-1.25, -0.5, 0.1))
    B.key(cam, F, location=(2.7, -0.2, 0.05))
    B.ease_all(cam, 'LINEAR')
    dust(140, ((-3, 6), (-1.5, 3), (-1.2, 1.2)), size=0.006, strength=6)
    B.area_light((0, -2, 2.5), (0.5, 0, 0), 120, size=3, color=(1, 0.9, 0.8))
    B.area_light((2, 2.5, 1), (0.5, 0, 0), 80, size=2, color=(0.4, 0.6, 1.0))
    B.area_light((5, -3, 2), (5, 0.6, 0), 300, size=3, color=(1, 0.85, 0.7))
    return F


def scene_speed():
    F = nframes("speed")
    B.reset(F)
    B.world_color((0.008, 0.012, 0.025))
    b = B.bullet(scale=0.4)
    b.rotation_euler = (0, rad(90), 0)
    b.location = (-0.22, 0, 0)
    b.keyframe_insert("rotation_euler", frame=1)
    b.rotation_euler = (rad(1440), rad(90), 0)
    b.keyframe_insert("rotation_euler", frame=F)
    B.ease_all(b, 'LINEAR')
    # supersonic shock cone: thin glass shell trailing back from the nose
    cone = B.lathe("Shock", [(0.0, 0.0), (0.08, -0.05), (0.6, -0.55), (1.6, -1.5)], segs=64)
    cone.rotation_euler = (0, rad(90), 0)
    cone.location = (0.24, 0, 0)
    cone.data.materials.append(B.xray_mat("ShockGlow", (0.45, 0.7, 1.0), 0.3, 0.05))
    cone.scale = (0.7, 0.7, 0.7)
    sol = cone.modifiers.new("S", 'SOLIDIFY')
    sol.thickness = 0.02
    # streaks rushing past (world moves, bullet holds still)
    rnd = random.Random(4)
    streak_m = B.emission_mat("Streak", (0.6, 0.75, 1.0), 6)
    for i in range(70):
        bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.004, depth=rnd.uniform(0.6, 1.8),
                                            rotation=(0, rad(90), 0))
        s = bpy.context.object
        s.data.materials.append(streak_m)
        y = rnd.uniform(-2, 4)
        z = rnd.uniform(-1.8, 1.8)
        if abs(z) < 0.25 and y < 0.6:
            z += 0.5 * (1 if z >= 0 else -1)
        speed = rnd.uniform(0.35, 0.6)
        x0 = rnd.uniform(-2, 14)
        B.key(s, 1, location=(x0, y, z))
        B.key(s, F, location=(x0 - speed * F, y, z))
        B.ease_all(s, 'LINEAR')
    ctr = bpy.data.objects.new("Ctr", None)
    bpy.context.collection.objects.link(ctr)
    ctr.location = (-0.15, 0, 0)
    cam = B.camera((0.6, -2.0, 0.35), (0, 0, 0), lens=24, dof_target=ctr, fstop=2.8)
    B.key(cam, 1, location=(1.0, -1.9, 0.5))
    B.key(cam, F, location=(-1.1, -1.5, 0.3))
    for o in (cam,):
        o.constraints.new('TRACK_TO').target = ctr
        o.constraints[0].track_axis = 'TRACK_NEGATIVE_Z'
        o.constraints[0].up_axis = 'UP_Y'
    B.area_light((0, -2, 2.5), (0, 0, 0), 150, size=2, color=(1, 0.9, 0.8))
    B.area_light((-1, 2, 0.5), (0, 0, 0), 120, size=2, color=(0.3, 0.5, 1.0))
    B.area_light((2, 0, -2), (0, 0, 0), 60, size=2, color=(1, 0.5, 0.3))
    return F


def _section_scene(F, cavity):
    B.world_color((0.01, 0.008, 0.008))
    layers, extra = thigh_section()
    z = 0.48
    cutter = tunnel_cutter(z)
    for o in layers:
        boolean(o, cutter)
    b = B.bullet(scale=0.17)
    b.rotation_euler = (0, rad(90), 0)
    b.location.y = 0.0
    hit, out = round(F * 0.18), round(F * 0.62)
    # bullet: approach fast, slow-mo through the thigh, leave fast
    B.key(b, 1, location=(-3.2, 0, z))
    B.key(b, hit, location=(-1.25, 0, z))
    B.key(b, out, location=(1.25, 0, z))
    B.key(b, F, location=(4.0, 0, z))
    B.ease_all(b, 'LINEAR')
    b.keyframe_insert("rotation_euler", frame=1)
    b.rotation_euler = (rad(900), rad(90), 0)
    b.keyframe_insert("rotation_euler", frame=F)
    # tunnel length tracks the bullet's base
    for f in range(1, F + 1):
        bpy.context.scene.frame_set(f)
        ln = max(0.001, b.location.x - 0.0 - cutter.location.x)
        if b.location.x > 1.4:
            ln = 3.0
        cutter.scale = (ln if b.location.x > cutter.location.x else 0.001, 1, 1)
        cutter.keyframe_insert("scale", frame=f)
    B.ease_all(cutter, 'LINEAR')
    if cavity:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1.0, location=(0, 0, z))
        cav = bpy.context.object
        cav.name = "Cavity"
        cav.data.materials.append(B.wound_mat())
        cav.hide_render = True
        cav.display_type = 'WIRE'
        for o in layers:
            boolean(o, cav)
        # grows behind the bullet, peaks, snaps back with a small rebound
        mid = (hit + out) // 2
        seq = [(1, 0.0, 0.0), (hit + 4, 0.0, 0.0), (mid, 0.9, 0.3), (out + 6, 1.15, 0.38),
               (out + 16, 0.4, 0.12), (out + 24, 0.75, 0.2), (out + 34, 0.0, 0.0)]
        for f, sx, s in seq:
            cav.scale = (max(sx, 0.001), max(s, 0.001), max(s, 0.001))
            cav.location.x = -0.25 + 0.15 * (f > mid)
            cav.keyframe_insert("scale", frame=f)
            cav.keyframe_insert("location", frame=f)
    # camera looks at the cut face, slowly pushing in
    cam = B.camera((0.0, -6.2, 1.3), (0, 0, 0.1), lens=38)
    B.key(cam, 1, location=(0.8, -6.2, 1.6))
    B.key(cam, F, location=(0.2, -4.6, 1.0))
    c = cam.constraints.new('TRACK_TO')
    tgt = bpy.data.objects.new("T", None)
    bpy.context.collection.objects.link(tgt)
    tgt.location = (0, 0, 0.15)
    c.target = tgt
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'
    B.cam_shake(cam, hit, hit + 10, amp=0.06, seed=3)
    B.area_light((-2.5, -4, 3), (0, 0, 0), 500, size=3, color=(1, 0.92, 0.85))
    B.area_light((3, -2, -1), (0, 0, 0), 200, size=3, color=(0.5, 0.65, 1.0))
    B.area_light((0, 3, 3), (0, 1, 0), 300, size=4, color=(1, 0.6, 0.5))
    return hit, out


def scene_perm():
    F = nframes("perm")
    B.reset(F)
    _section_scene(F, cavity=False)
    return F


def scene_temp():
    F = nframes("temp")
    B.reset(F)
    _section_scene(F, cavity=True)
    return F


def scene_movies():
    F = nframes("movies")
    B.reset(F)
    B.world_color((0.015, 0.015, 0.02))
    floor = B.floor_backdrop((0.004, 0.004, 0.005), z=0)
    B.bsdf(floor.data.materials[0]).inputs["Roughness"].default_value = 0.25
    # pedestals
    pm = B.mat("Ped", (0.08, 0.08, 0.09), rough=0.3)
    for x in (-1.1, 1.1):
        bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.55, depth=0.3, location=(x, 0, 0.15))
        bpy.context.object.data.materials.append(pm)
    b = B.bullet(scale=0.5)
    b.location = (-1.1, 0, 0.3)
    b.keyframe_insert("rotation_euler", frame=1)
    b.rotation_euler = (0, 0, rad(200))
    b.keyframe_insert("rotation_euler", frame=F)
    # baseball with red stitching
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=0.37, location=(1.1, 0, 0.67))
    ball = bpy.context.object
    bpy.ops.object.shade_smooth()
    bm = B.mat("Ball", (0.9, 0.88, 0.82), rough=0.6)
    ball.data.materials.append(bm)
    pts = []
    for i in range(200):
        t = 2 * math.pi * i / 200
        # classic tennis/baseball seam curve
        a, bb = 0.8, 0.2
        x = a * math.cos(t) + bb * math.cos(3 * t)
        y = a * math.sin(t) - bb * math.sin(3 * t)
        zz = 2 * math.sqrt(a * bb) * math.sin(2 * t)
        v = Vector((x, y, zz)).normalized() * 0.372
        pts.append(v)
    cd = bpy.data.curves.new("Seam", 'CURVE')
    cd.dimensions = '3D'
    sp = cd.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for p, v in zip(sp.points, pts):
        p.co = (*v, 1)
    sp.use_cyclic_u = True
    cd.bevel_depth = 0.012
    seam = bpy.data.objects.new("Seam", cd)
    bpy.context.collection.objects.link(seam)
    seam.parent = ball
    seam.location = (0, 0, 0)
    seam.data.materials.append(B.mat("Stitch", (0.7, 0.02, 0.02), rough=0.5))
    ball.keyframe_insert("rotation_euler", frame=1)
    ball.rotation_euler = (rad(20), 0, rad(-160))
    ball.keyframe_insert("rotation_euler", frame=F)
    # momentum bars: bullet ~3 kg*m/s (8 g @ 370 m/s), fastball ~6 kg*m/s (145 g @ 40 m/s)
    gm = B.mat("BarB", (0.95, 0.4, 0.08), rough=0.3, emit=(0.95, 0.35, 0.05), emit_strength=0.35)
    bm2 = B.mat("BarW", (0.1, 0.4, 1.0), rough=0.3, emit=(0.05, 0.3, 1.0), emit_strength=0.35)
    start = round(F * 0.42)
    for x, h, m in ((-1.1, 0.9, gm), (1.1, 1.8, bm2)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, 0.9, 0))
        bar = bpy.context.object
        bar.data.materials.append(m)
        bar.data.vertices.foreach_set("co", [c for v in bar.data.vertices for c in (v.co.x * 0.5, v.co.y * 0.3, v.co.z + 0.5)])
        B.key(bar, 1, scale=(1, 1, 0.001))
        B.key(bar, start, scale=(1, 1, 0.001))
        B.key(bar, start + 30, scale=(1, 1, h))
    cam = B.camera((0, -6.3, 2.1), (0, 0, 0.9), lens=32)
    B.key(cam, 1, location=(0.3, -6.6, 2.2))
    B.key(cam, F, location=(-0.2, -5.6, 1.9))
    c = cam.constraints.new('TRACK_TO')
    tgt = bpy.data.objects.new("T", None)
    bpy.context.collection.objects.link(tgt)
    tgt.location = (0, 0.3, 0.95)
    c.target = tgt
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'
    B.area_light((-1.1, -1.5, 3), (-1.1, 0, 0.4), 90, size=1.0, color=(1, 0.9, 0.8))
    B.area_light((1.1, -1.5, 3), (1.1, 0, 0.6), 90, size=1.0, color=(1, 0.95, 0.9))
    B.area_light((0, 3, 2), (0, 0, 0.5), 150, size=4, color=(0.5, 0.6, 1.0))
    return F


def scene_adren():
    F = nframes("adren")
    B.reset(F)
    B.world_color((0.03, 0.006, 0.006))
    # kidney
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1, location=(0, 0, 0))
    k = bpy.context.object
    bpy.ops.object.shade_smooth()
    k.scale = (0.55, 0.35, 0.95)
    sd = k.modifiers.new("Bend", 'SIMPLE_DEFORM')
    sd.deform_method = 'BEND'
    sd.angle = rad(-50)
    sd.deform_axis = 'Y'
    km = B.mat("Kidney", (0.42, 0.1, 0.07), rough=0.25, sss=0.3, coat=0.6)
    k.data.materials.append(km)
    # adrenal gland: flattened yellow cap on top
    bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=0.42, radius2=0.05, depth=0.55, location=(-0.05, 0, 1.05))
    g = bpy.context.object
    g.scale = (1, 0.45, 1)
    sub = g.modifiers.new("Sub", 'SUBSURF')
    sub.levels = sub.render_levels = 2
    bpy.ops.object.shade_smooth()
    gm = B.mat("Adrenal", (0.9, 0.55, 0.08), rough=0.35, sss=0.3, emit=(1.0, 0.55, 0.05), emit_strength=0.0)
    g.data.materials.append(gm)
    em = B.bsdf(gm).inputs["Emission Strength"]
    pulse = round(F * 0.2)
    for f, v in ((1, 0.0), (pulse, 0.0), (pulse + 8, 1.2), (pulse + 20, 0.4), (pulse + 30, 1.2), (F, 0.8)):
        em.default_value = v
        em.keyframe_insert("default_value", frame=f)
    # adrenaline molecules stream up and out
    rnd = random.Random(7)
    am = B.emission_mat("Adrenaline", (1.0, 0.6, 0.08), 2.5)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.025)
    proto = bpy.context.object
    proto.data.materials.append(am)
    for i in range(160):
        o = proto if i == 0 else proto.copy()
        if i:
            o.animation_data_clear()
            bpy.context.collection.objects.link(o)
        t0 = rnd.randint(pulse, F - 10)
        ang = rnd.uniform(0, 2 * math.pi)
        spread = rnd.uniform(0.2, 1.5)
        end = Vector((math.cos(ang) * spread * 1.4, math.sin(ang) * spread * 0.6, 1.2 + rnd.uniform(1.0, 2.6)))
        o.location = (-0.05, 0, 1.15)
        o.scale = (0.001,) * 3
        o.keyframe_insert("location", frame=1)
        o.keyframe_insert("scale", frame=1)
        o.keyframe_insert("location", frame=t0)
        o.keyframe_insert("scale", frame=t0)
        s = rnd.uniform(0.6, 1.4)
        o.scale = (s, s, s)
        o.keyframe_insert("scale", frame=t0 + 3)
        o.location = end
        o.keyframe_insert("location", frame=t0 + rnd.randint(24, 48))
    # renal vessels
    vm = B.mat("Vessel", (0.55, 0.04, 0.04), rough=0.3, coat=0.5)
    for zoff, col in ((0.1, vm), (-0.15, B.mat("V2", (0.12, 0.08, 0.35), rough=0.3, coat=0.5))):
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.09, depth=2.5, location=(1.4, 0.05, zoff),
                                            rotation=(0, rad(90), 0))
        bpy.context.object.data.materials.append(col)
        bpy.ops.object.shade_smooth()
    cam = B.camera((0.4, -4.4, 1.3), (0, 0, 0.9), lens=32)
    B.key(cam, 1, location=(0.8, -4.6, 0.9))
    B.key(cam, F, location=(0.1, -3.6, 1.6))
    c = cam.constraints.new('TRACK_TO')
    tgt = bpy.data.objects.new("T", None)
    bpy.context.collection.objects.link(tgt)
    B.key(tgt, 1, location=(0, 0, 0.5))
    B.key(tgt, F, location=(0, 0, 1.4))
    c.target = tgt
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'
    B.area_light((-2, -3, 3), (0, 0, 0.5), 300, size=3, color=(1, 0.9, 0.85))
    B.area_light((2.5, 2, 1), (0, 0, 0.5), 200, size=3, color=(1, 0.4, 0.3))
    dust(60, ((-3, 3), (-1, 4), (-2, 4)), size=0.012, color=(1, 0.4, 0.3), strength=0.8)
    return F


def scene_artery():
    F = nframes("artery")
    B.reset(F, samples=14)
    B.world_color((0.02, 0.003, 0.003))
    L = 9.0
    R = 0.75
    # vessel wall, cut open towards the camera
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=R, depth=L, rotation=(0, rad(90), 0), end_fill_type='NOTHING')
    wall = bpy.context.object
    bpy.ops.object.transform_apply(rotation=True)
    me = wall.data
    # remove the half facing the camera (y < -0.2)
    import bmesh as _bm
    bm2 = _bm.new()
    bm2.from_mesh(me)
    _bm.ops.delete(bm2, geom=[v for v in bm2.verts if v.co.y < -0.3 * R], context='VERTS')
    bm2.to_mesh(me)
    bm2.free()
    sol = wall.modifiers.new("Sol", 'SOLIDIFY')
    sol.thickness = 0.12
    sub = wall.modifiers.new("Sub", 'SUBSURF')
    sub.levels = sub.render_levels = 1
    bpy.ops.object.shade_smooth()
    wm = B.mat("ArteryInner", (0.55, 0.08, 0.07), rough=0.25, sss=0.4, coat=0.7)
    n = B.node(wm, "ShaderNodeTexNoise", (-600, 0))
    n.inputs["Scale"].default_value = 6
    n.inputs["Detail"].default_value = 6
    bb = B.node(wm, "ShaderNodeBump", (-300, -200))
    bb.inputs["Strength"].default_value = 0.25
    B.link(wm, n.outputs["Fac"], bb.inputs["Height"])
    B.link(wm, bb.outputs["Normal"], B.bsdf(wm).inputs["Normal"])
    wall.data.materials.append(wm)
    # the tear: a sphere cutter that opens in the top wall when the bullet passes
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.28, location=(0.4, 0.15, R))
    hole = bpy.context.object
    hole.hide_render = True
    hole.display_type = 'WIRE'
    hole.data.materials.append(B.wound_mat())
    hit = round(F * 0.3)
    B.key(hole, 1, scale=(0.001,) * 3)
    B.key(hole, hit, scale=(0.001,) * 3)
    B.key(hole, hit + 4, scale=(1.0, 0.8, 1.0))
    boolean(wall, hole)
    # bullet drops through the top wall (seen side-on), out of frame
    b = B.bullet(scale=0.35)
    b.rotation_euler = (rad(180), 0, 0)
    B.key(b, 1, location=(0.4, 0.15, 4.5))
    B.key(b, hit, location=(0.4, 0.15, R + 0.2))
    B.key(b, hit + 6, location=(0.4, 0.15, -3.5))
    B.ease_all(b, 'LINEAR')
    # blood cells flowing along +X; once the hole opens, cells near it escape upward
    rnd = random.Random(11)
    proto = rbc_proto()
    proto.scale = (0.11,) * 3
    hx = 0.4
    v = 0.055
    for i in range(170):
        o = proto if i == 0 else proto.copy()
        if i:
            o.animation_data_clear()
            bpy.context.collection.objects.link(o)
        r = R * 0.8 * math.sqrt(rnd.random())
        a = rnd.uniform(0, 2 * math.pi)
        y, z = r * math.cos(a) * 0.6 + 0.12, r * math.sin(a)
        x0 = rnd.uniform(-L / 2 - 4, L / 2)
        rot0 = Vector((rnd.uniform(0, 6), rnd.uniform(0, 6), rnd.uniform(0, 6)))
        o.rotation_euler = rot0
        o.keyframe_insert("rotation_euler", frame=1)
        o.rotation_euler = rot0 + Vector((rnd.uniform(-3, 3), rnd.uniform(-3, 3), 0))
        o.keyframe_insert("rotation_euler", frame=F)
        o.location = (x0, y, z)
        o.keyframe_insert("location", frame=1)
        # frame at which this cell reaches the tear
        f_at = 1 + (hx - x0) / v
        escapes = rnd.random() < 0.6 and f_at > hit + 2 and f_at < F
        if escapes:
            f_at = int(f_at)
            o.location = (hx - 0.1 + rnd.uniform(-0.1, 0.1), 0.15 + rnd.uniform(-0.15, 0.15), R * 0.6)
            o.keyframe_insert("location", frame=f_at)
            out = Vector((hx + rnd.uniform(-1.2, 1.6), rnd.uniform(-0.6, 0.9), R + rnd.uniform(1.5, 3.5)))
            o.location = out
            o.keyframe_insert("location", frame=min(F + 20, f_at + rnd.randint(20, 40)))
        else:
            o.location = (x0 + v * (F - 1), y, z)
            o.keyframe_insert("location", frame=F)
        B.ease_all(o, 'LINEAR')
    cam = B.camera((0.0, -4.3, 0.9), (0.3, 0.2, 0.3), lens=26)
    B.key(cam, 1, location=(-1.4, -4.3, 0.6))
    B.key(cam, F, location=(0.9, -3.4, 1.4))
    c = cam.constraints.new('TRACK_TO')
    tgt = bpy.data.objects.new("T", None)
    bpy.context.collection.objects.link(tgt)
    tgt.location = (0.4, 0.2, 0.6)
    c.target = tgt
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'
    B.cam_shake(cam, hit, hit + 10, amp=0.08, seed=5)
    B.area_light((0, -3, 3), (0, 0, 0), 450, size=4, color=(1, 0.85, 0.8))
    B.point_light((0.5, 0.3, 0.0), 40, color=(1, 0.35, 0.3), radius=0.5)
    B.area_light((0, 2, 3), (0.4, 0, 1), 250, size=3, color=(1, 0.6, 0.5))
    return F


def scene_shock():
    F = nframes("shock")
    B.reset(F)
    B.world_color((0.012, 0.01, 0.015))
    half = F // 2
    # --- part 1: racing heart (visible first half)
    h = heart_model()
    h.location = (0, 0, -0.5)
    h.rotation_euler = (0, rad(15), rad(-20))
    f = 1
    period = 18.0
    while f < half + 2:
        B.key(h, int(f), scale=(1, 1, 1))
        B.key(h, int(f + period * 0.25), scale=(0.88, 0.9, 0.86))
        B.key(h, int(f + period * 0.45), scale=(1.02, 1.02, 1.03))
        f += period
        period = max(9.0, period * 0.85)
    # --- part 2: brain losing oxygen (placed off to the side, camera cuts)
    brain, mix = brain_object()
    brain.location = (20, 0, 0)
    brain.rotation_euler = (0, 0, rad(200))
    fac = mix.inputs["Factor"]
    fac.default_value = 0.0
    fac.keyframe_insert("default_value", frame=half)
    fac.default_value = 0.85
    fac.keyframe_insert("default_value", frame=F - 10)
    brain.keyframe_insert("rotation_euler", frame=half)
    brain.rotation_euler = (0, 0, rad(235))
    brain.keyframe_insert("rotation_euler", frame=F)
    # oxygen sparks around the brain fade out
    om = B.emission_mat("O2", (0.4, 0.75, 1.0), 6)
    strength = om.node_tree.nodes["Emission"].inputs[1]
    strength.keyframe_insert("default_value", frame=half)
    strength.default_value = 0.0
    strength.keyframe_insert("default_value", frame=F - 15)
    rnd = random.Random(2)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.03)
    proto = bpy.context.object
    proto.data.materials.append(om)
    for i in range(90):
        o = proto if i == 0 else proto.copy()
        if i:
            o.animation_data_clear()
            bpy.context.collection.objects.link(o)
        d = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.7, 1))).normalized()
        o.location = Vector((20, 0, 0)) + d * rnd.uniform(1.4, 2.4)
        o.keyframe_insert("location", frame=half)
        o.location = Vector((20, 0, 0)) + d * rnd.uniform(1.2, 1.6)
        o.keyframe_insert("location", frame=F)
    cam = B.camera((0, -6, 0.6), (0, 0, 0.3), lens=28)
    for fr, loc, tg in ((1, (0.5, -7.2, 1.2), (0, 0, 0.6)), (half - 1, (-0.4, -5.8, 0.8), (0, 0, 0.6)),
                        (half, (21.6, -5.4, 2.4), (20, 0, -0.1)), (F, (20.9, -4.4, 1.7), (20, 0, -0.15))):
        cam.location = loc
        B.look_at(cam, tg)
        cam.keyframe_insert("location", frame=fr)
        cam.keyframe_insert("rotation_euler", frame=fr)
    for fc in B.fcurves(cam.animation_data.action):
        for kp in fc.keyframe_points:
            kp.interpolation = 'CONSTANT' if int(kp.co.x) == half - 1 else 'LINEAR'
    for x in (0, 20):
        B.area_light((x - 2.5, -3, 3), (x, 0, 0), 450, size=3, color=(1, 0.9, 0.85))
        B.area_light((x + 3, 2, 1), (x, 0, 0), 300, size=3, color=(0.4, 0.55, 1.0))
        B.area_light((x, 3, -2), (x, 0, 0), 150, size=3, color=(1, 0.4, 0.3))
    return F


def scene_tq():
    F = nframes("tq")
    B.reset(F)
    B.world_color((0.015, 0.015, 0.018))
    # thigh lying horizontally along X
    leg = cylinder("Thigh", 1.0, 7, (0, 0, 0), (0, rad(90), 0), material=B.skin_mat())
    tp = leg.modifiers.new("Taper", 'SIMPLE_DEFORM')
    tp.deform_method = 'TAPER'
    tp.deform_axis = 'Z'
    tp.factor = -0.06
    # wound
    bpy.ops.mesh.primitive_circle_add(vertices=32, radius=0.13, fill_type='NGON', location=(1.0, -0.945, 0.1),
                                      rotation=(rad(90), 0, 0))
    w = bpy.context.object
    w.data.materials.append(B.wound_mat())
    # tourniquet band a few inches above the wound (towards the hip, -X)
    bpy.ops.mesh.primitive_torus_add(major_radius=1.12, minor_radius=0.09, major_segments=96, minor_segments=16,
                                     location=(-0.05, 0, 0), rotation=(0, rad(90), 0))
    band = bpy.context.object
    band.scale = (1, 1, 1)
    band.data.materials.append(B.mat("Strap", (0.02, 0.02, 0.02), rough=0.7))
    bpy.ops.object.shade_smooth()
    # windlass rod
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.06, depth=0.9, location=(-0.05, -1.18, 0),
                                        rotation=(0, rad(90), 0))
    rod = bpy.context.object
    rod.data.materials.append(B.mat("Rod", (0.1, 0.1, 0.1), rough=0.4, metal=0.5))
    bpy.ops.object.shade_smooth()
    t0, t1 = round(F * 0.3), round(F * 0.55)
    B.key(band, 1, scale=(1, 1, 1))
    B.key(band, t0, scale=(1, 1, 1))
    B.key(band, t1, scale=(0.94, 0.94, 1.0))
    rod.keyframe_insert("rotation_euler", frame=t0)
    rod.rotation_euler = (rad(540), rad(90), 0)
    rod.keyframe_insert("rotation_euler", frame=t1)
    B.key(rod, t0, location=(-0.05, -1.18, 0))
    B.key(rod, t1, location=(-0.05, -1.11, 0))
    # blood drips from the wound until the tourniquet is tight
    bm = B.blood_mat()
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.06)
    proto = bpy.context.object
    proto.data.materials.append(bm)
    bpy.ops.object.shade_smooth()
    f = 1
    i = 0
    while f < t1 + 8:
        o = proto if i == 0 else proto.copy()
        if i:
            o.animation_data_clear()
            bpy.context.collection.objects.link(o)
        o.scale = (1, 1, 1.4)
        B.key(o, 1, location=(1.0, -0.97, 0.05), scale=(0.001,) * 3)
        B.key(o, int(f), location=(1.0, -0.97, 0.05), scale=(0.001,) * 3)
        B.key(o, int(f) + 4, location=(1.0, -0.99, -0.02), scale=(1, 1, 1.4))
        o.location = (1.0, -1.0, -3.0)
        o.keyframe_insert("location", frame=int(f) + 14)
        f += 6 if f < t0 else 10
        i += 1
    # blood pooled below
    cam = B.camera((0.2, -5.2, 0.8), (0, 0, 0), lens=30)
    B.key(cam, 1, location=(1.2, -4.6, 1.3))
    B.key(cam, F, location=(0.0, -3.8, 0.7))
    c = cam.constraints.new('TRACK_TO')
    tgt = bpy.data.objects.new("T", None)
    bpy.context.collection.objects.link(tgt)
    B.key(tgt, 1, location=(0.5, 0, -0.2))
    B.key(tgt, F, location=(0.35, 0, -0.1))
    c.target = tgt
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'
    B.area_light((-1, -3, 3), (0, 0, 0), 450, size=3, color=(1, 0.92, 0.85))
    B.area_light((3, 2, 1), (0, 0, 0), 250, size=3, color=(0.45, 0.6, 1.0))
    B.area_light((0, 3, -1), (0, 0, 0), 120, size=3, color=(1, 0.5, 0.4))
    return F


def scene_bullet():
    F = nframes("bullet")
    B.reset(F, samples=12)
    B.world_color((0.0, 0.004, 0.012))
    # X-ray: translucent leg outline, glowing femur, bright bullet lodged in muscle
    leg = cylinder("LegX", 1.0, 10, (0, 0, 0), material=B.xray_mat("SkinX", (0.25, 0.55, 1.0), 0.7, 0.12))
    leg.scale = (1, 0.85, 1)
    tp = leg.modifiers.new("Taper", 'SIMPLE_DEFORM')
    tp.deform_method = 'TAPER'
    tp.deform_axis = 'Z'
    tp.factor = 0.05
    # femur: shaft + condyle bulge + femoral head offset
    prof = [(0.0, -3.2), (0.42, -3.1), (0.45, -2.8), (0.3, -2.4), (0.22, -1.8), (0.2, 0.0), (0.22, 1.8),
            (0.3, 2.3), (0.34, 2.6), (0.2, 2.9), (0.0, 3.0)]
    fem = B.lathe("Femur", prof, segs=48)
    fem.rotation_euler = (0, rad(-6), 0)
    fem.data.materials.append(B.xray_mat("BoneX", (0.75, 0.88, 1.0), 5.0, 0.5))
    b = B.bullet(scale=0.32)
    b.location = (0.5, 0.1, 0.5)
    b.rotation_euler = (rad(90), rad(25), rad(-30))
    b.data.materials.clear()
    b.data.materials.append(B.xray_mat("BulletX", (1.0, 0.95, 0.85), 14.0, 0.75))
    # slow orbit
    pivot = bpy.data.objects.new("Pivot", None)
    bpy.context.collection.objects.link(pivot)
    cam = B.camera((0, -7.0, 0.6), (0, 0, 0.3), lens=30)
    cam.parent = pivot
    pivot.keyframe_insert("rotation_euler", frame=1)
    pivot.rotation_euler = (0, 0, rad(70))
    pivot.keyframe_insert("rotation_euler", frame=F)
    B.ease_all(pivot, 'LINEAR')
    B.key(cam, 1, location=(0, -7.6, 0.8))
    B.key(cam, F, location=(0, -5.2, 0.5))
    c = cam.constraints.new('TRACK_TO')
    tgt = bpy.data.objects.new("T", None)
    bpy.context.collection.objects.link(tgt)
    B.key(tgt, 1, location=(0, 0, 0.2))
    B.key(tgt, F, location=(0.35, 0, 0.5))
    c.target = tgt
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'
    return F


SCENES = {
    "hook": scene_hook, "speed": scene_speed, "perm": scene_perm, "temp": scene_temp,
    "movies": scene_movies, "adren": scene_adren, "artery": scene_artery, "shock": scene_shock,
    "tq": scene_tq, "bullet": scene_bullet,
}

if __name__ == "__main__":
    sid = sys.argv[1]
    F = SCENES[sid]()
    out = os.path.join(ROOT, "renders", sid)
    if len(sys.argv) > 2:
        for fr in sys.argv[2].split(","):
            fr = int(fr) if fr not in ("mid", "end") else (F // 2 if fr == "mid" else F)
            B.render(out, fr)
    else:
        B.render(out)
    print("DONE", sid, F)
