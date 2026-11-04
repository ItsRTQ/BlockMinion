"""3D GeckoLib armor for a material (armor_style == "3d"): the worn model is a Blockbench model with the eight
GeckoLib armor bones instead of a painted layer. Generator: <Mat>ArmorItem (ArmorItem + GeoItem with a
GeoRenderProvider), client <Mat>ArmorRenderer (GeoArmorRenderer + DefaultedItemGeoModel("armor/<mat>")),
placeholder geo/animation/texture under geo|animations|textures/item/armor/. Designer task ARMOR3D:<mat>
edits the shipped template (resources/blockbench/armor_template.bbmodel) and must render it; the controller
validates the bone names against the pieces and installs the exports.
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path

from .spec import Spec, Material
from .state import Store, StateError
from .validation import InputError

ARMOR_BONES = ("armorHead", "armorBody", "armorRightArm", "armorLeftArm", "armorRightLeg", "armorLeftLeg", "armorRightBoot", "armorLeftBoot")
PIECE_BONES = {"helmet": ("armorHead",), "chestplate": ("armorBody", "armorRightArm", "armorLeftArm"), "leggings": ("armorRightLeg", "armorLeftLeg"), "boots": ("armorRightBoot", "armorLeftBoot")}
TEMPLATE_DIR = Path(__file__).resolve().parent / "resources" / "blockbench"


def cls(ident: str) -> str:
    return "".join(p.capitalize() for p in ident.split("_"))


def armor3d_materials(spec: Spec) -> list[Material]:
    return [m for m in spec.materials if m.armor and m.armor_style == "3d"]


def armor_item_java(spec: Spec, m: Material) -> str:
    c = cls(m.identifier)
    return "\n".join([
        f"package {spec.package}.gear;", "",
        f"import {spec.package}.client.{c}ArmorRenderer;",
        "import net.minecraft.core.Holder;", "import net.minecraft.world.entity.EquipmentSlot;", "import net.minecraft.world.entity.LivingEntity;",
        "import net.minecraft.world.item.ArmorItem;", "import net.minecraft.world.item.ArmorMaterial;", "import net.minecraft.world.item.ItemStack;",
        "import net.minecraft.client.model.HumanoidModel;", "import org.jetbrains.annotations.Nullable;",
        "import software.bernie.geckolib.animatable.GeoItem;", "import software.bernie.geckolib.animatable.client.GeoRenderProvider;",
        "import software.bernie.geckolib.animatable.instance.AnimatableInstanceCache;", "import software.bernie.geckolib.animation.AnimatableManager;",
        "import software.bernie.geckolib.animation.AnimationController;", "import software.bernie.geckolib.animation.PlayState;",
        "import software.bernie.geckolib.animation.RawAnimation;", "import software.bernie.geckolib.renderer.GeoArmorRenderer;",
        "import software.bernie.geckolib.util.GeckoLibUtil;", "import java.util.function.Consumer;", "",
        f"/** GeckoLib 3D armor for material '{m.identifier}'. Model: assets/{spec.mod_id}/geo/item/armor/{m.identifier}.geo.json (designed in Blockbench). */",
        f"public class {c}ArmorItem extends ArmorItem implements GeoItem {{",
        f'    private static final RawAnimation IDLE = RawAnimation.begin().thenLoop("animation.{m.identifier}_armor.idle");',
        "    private final AnimatableInstanceCache cache = GeckoLibUtil.createInstanceCache(this);", "",
        f"    public {c}ArmorItem(Holder<ArmorMaterial> material, ArmorItem.Type type, Properties properties) {{ super(material, type, properties); }}", "",
        "    @Override",
        "    public void createGeoRenderer(Consumer<GeoRenderProvider> consumer) {",
        "        consumer.accept(new GeoRenderProvider() {",
        "            private GeoArmorRenderer<?> renderer;", "",
        "            @Override",
        "            public <T extends LivingEntity> HumanoidModel<?> getGeoArmorRenderer(@Nullable T livingEntity, ItemStack itemStack, @Nullable EquipmentSlot equipmentSlot, @Nullable HumanoidModel<T> original) {",
        f"                if (this.renderer == null) this.renderer = new {c}ArmorRenderer();",
        "                return this.renderer;",
        "            }", "        });", "    }", "",
        "    @Override",
        "    public void registerControllers(AnimatableManager.ControllerRegistrar controllers) {",
        '        controllers.add(new AnimationController<>(this, "base", 20, state -> state.setAndContinue(IDLE)));',
        "    }", "",
        "    @Override",
        "    public AnimatableInstanceCache getAnimatableInstanceCache() { return this.cache; }",
        "}", ""])


def armor_renderer_java(spec: Spec, m: Material) -> str:
    c = cls(m.identifier)
    return "\n".join([
        f"package {spec.package}.client;", "",
        f"import {spec.package}.ModMain;", f"import {spec.package}.gear.{c}ArmorItem;",
        "import net.minecraft.resources.ResourceLocation;",
        "import software.bernie.geckolib.model.DefaultedItemGeoModel;", "import software.bernie.geckolib.renderer.GeoArmorRenderer;", "",
        f"public class {c}ArmorRenderer extends GeoArmorRenderer<{c}ArmorItem> {{",
        f"    public {c}ArmorRenderer() {{",
        f'        super(new DefaultedItemGeoModel<>(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "armor/{m.identifier}")));',
        "    }", "}", ""])


def placeholder_armor_geo(m: Material) -> dict:
    geo = json.loads((TEMPLATE_DIR / "armor_template.geo.json").read_text(encoding="utf8"))
    geo["minecraft:geometry"][0]["description"]["identifier"] = f"geometry.{m.identifier}_armor"
    return geo


def placeholder_armor_animation(m: Material) -> dict:
    return {"format_version": "1.8.0", "geckolib_format_version": 2, "animations": {f"animation.{m.identifier}_armor.idle": {"loop": True, "animation_length": 1.0, "bones": {}}}}


def armor3d_assets(spec: Spec) -> dict[str, bytes]:
    """Relative paths under src/main/resources -> bytes, for every 3d material."""
    from .textures import material_colors, png_from_pixels
    out: dict[str, bytes] = {}
    a = f"assets/{spec.mod_id}"
    for m in armor3d_materials(spec):
        base, acc = material_colors(spec.mod_id + "/" + m.identifier, m.color or None, m.accent or None)
        px = [[(0, 0, 0, 0)] * 64 for _ in range(64)]
        def fill(x0, y0, w, h, c):
            for y in range(y0, y0 + h):
                for x in range(x0, x0 + w): px[y][x] = (*c, 255)
        dark = tuple(int(v * 0.75) for v in base)
        fill(0, 0, 32, 16, base); fill(16, 16, 24, 16, base); fill(40, 16, 16, 16, acc); fill(32, 48, 16, 16, acc)
        fill(0, 16, 16, 16, dark); fill(16, 48, 16, 16, dark); fill(0, 32, 16, 16, base); fill(16, 32, 16, 16, base)
        out[f"{a}/geo/item/armor/{m.identifier}.geo.json"] = (json.dumps(placeholder_armor_geo(m), indent=2) + "\n").encode()
        out[f"{a}/animations/item/armor/{m.identifier}.animation.json"] = (json.dumps(placeholder_armor_animation(m), indent=2) + "\n").encode()
        out[f"{a}/textures/item/armor/{m.identifier}.png"] = png_from_pixels(64, 64, px)
    return out


# ---- designer task ----
ARMOR3D_INSTRUCTIONS = """
## Your job on this task (designer — 3D GeckoLib armor for material `<material>`)
`models/<material>_armor.bbmodel` is the GeckoLib armor template: eight bones with the exact names GeckoLib binds to
the player (armorHead, armorBody, armorRightArm, armorLeftArm, armorRightLeg, armorLeftLeg, armorRightBoot,
armorLeftBoot), each with a base cube. DO NOT rename, move or delete the bones or their pivots. Design the armor by
editing the base cubes and ADDING cubes under those bones: a helmet crest or visor under armorHead, pauldrons
under the arm bones, a chest plate / belt / tassets under armorBody, greaves and boot plates under the leg and
boot bones. Keep every cube within ~6 blocks-pixels of its bone so it moves with the limb. Only the bones for
the pieces this set has matter (listed in the task), but leave the others in place.
Texture: 64x64 (the template's UV layout); paint `models/<material>_armor.png` with a stdlib script in the mod's
theme and set it with `bbmodel_geckolib_set_texture`. Match the palette of the set's inventory icons.
Deliverables in `models/`: `<material>_armor.bbmodel`, `<material>_armor.geo.json`
(`bbmodel_geckolib_export_geometry`), `<material>_armor.animation.json` (`bbmodel_geckolib_export_animations`;
an idle animation named `animation.<material>_armor.idle` must exist, even if static — add it with
`bbmodel_geckolib_upsert_animation`), `<material>_armor.png`, and at least one render `<material>_armor_render.png`
(`bbmodel_render`) that you looked at and corrected before finishing. Report them all in `changed_files`.
Never touch `src/` or `assets/`; the controller installs the files.
"""


def request_armor3d(store: Store, pid: str, material: str, notes: str = "") -> dict:
    from .spec import read_spec
    proj = store.project(pid)
    if proj["status"] not in ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"):
        raise StateError("Generate the project first")
    spec = read_spec(proj["spec"])
    m = next((x for x in spec.materials if x.identifier == material), None)
    if m is None or not m.armor or m.armor_style != "3d":
        raise InputError(f"{material!r} is not a material with 3D armor (set armor_style to 3d)")
    ws = Path(proj["root"]); (ws / "models").mkdir(exist_ok=True)
    target = ws / "models" / f"{material}_armor.bbmodel"
    if not target.is_file():
        shutil.copyfile(TEMPLATE_DIR / "armor_template.bbmodel", target)
    n = sum(1 for t in store.tasks(pid) if f":ARMOR3D:{material}" in t["id"]) + 1
    task_id = f"{pid}:ARMOR3D:{material}" + (f":{n}" if n > 1 else "")
    lines = [f"Material: {material} ({m.label}); pieces: {', '.join(m.armor)}; bones that matter: " + ", ".join(b for p in m.armor for b in PIECE_BONES[p])]
    prior = [e["payload"].get("notes", "") for e in store.events(pid, 300) if e["kind"] == "ARMOR3D_REQUESTED" and e["payload"].get("material") == material and e["payload"].get("notes")]
    if notes.strip():
        lines += ["", "User notes for this round:", notes.strip()[:800]]
    if prior:
        lines += ["", "Earlier user notes (apply them too):"] + [f"- {p}" for p in prior[-5:]]
    store.add_task(pid, task_id, "designer", f"Design 3D armor model for {m.label}")
    with store.tx() as con:
        con.execute("INSERT OR IGNORE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(lines)))
    store.add_event(pid, "user", "ARMOR3D_REQUESTED", {"task": task_id, "material": material, "notes": notes[:300]})
    return {"task": task_id, "material": material, "next": {"action": "dispatch", "payload": {"task": task_id}}}


def validate_armor3d_files(ws: Path, material: str, pieces: tuple) -> dict:
    root = ws / "models"
    files = {k: root / f"{material}_armor.{ext}" for k, ext in (("bbmodel", "bbmodel"), ("geo", "geo.json"), ("anim", "animation.json"), ("png", "png"))}
    missing = [f.name for f in files.values() if not f.is_file()]
    if missing:
        raise InputError(f"designer deliverables missing in models/: {', '.join(missing)}")
    renders = sorted(root.glob(f"{material}_armor_render*.png"))
    if not renders:
        raise InputError(f"no render found (models/{material}_armor_render.png): the designer must look at the armor before finishing")
    geo = json.loads(files["geo"].read_text(encoding="utf8"))
    try:
        g = geo["minecraft:geometry"][0]; desc = g["description"]; bones = {b["name"] for b in g["bones"]}
    except (KeyError, IndexError, TypeError):
        raise InputError("geo.json is not Bedrock 1.12.0 geometry")
    if desc.get("identifier") != f"geometry.{material}_armor":
        raise InputError(f"geo identifier must be geometry.{material}_armor, got {desc.get('identifier')!r}")
    needed = {b for p in pieces for b in PIECE_BONES[p]}
    lost = sorted(needed - bones)
    if lost:
        raise InputError(f"geo.json lost required armor bones: {lost} (never rename or delete the template bones)")
    stray = sorted(bones - set(ARMOR_BONES))
    top_level = {b["name"] for b in g["bones"] if not b.get("parent")}
    bad_roots = sorted(top_level - set(ARMOR_BONES))
    if bad_roots:
        raise InputError(f"extra root bones are not rendered by GeckoLib armor: {bad_roots}; parent them under one of the eight armor bones")
    anim = json.loads(files["anim"].read_text(encoding="utf8"))
    if f"animation.{material}_armor.idle" not in (anim.get("animations") or {}):
        raise InputError(f"animation.json lacks animation.{material}_armor.idle")
    png = files["png"].read_bytes()
    w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    if (desc.get("texture_width"), desc.get("texture_height")) != (w, h):
        raise InputError(f"texture is {w}x{h} but geo declares {desc.get('texture_width')}x{desc.get('texture_height')}")
    cubes = sum(len(b.get("cubes", [])) for b in g["bones"])
    return {"bones": sorted(bones), "extra_bones": stray, "cubes": cubes, "texture": [w, h], "renders": [str(r.relative_to(ws)).replace("\\", "/") for r in renders],
            "files": {k: str(v.relative_to(ws)).replace("\\", "/") for k, v in files.items()}}


def install_armor3d(store: Store, pid: str, task_id: str, material: str, *, run_id: str, actor: str) -> dict:
    from .spec import read_spec
    from .fabric import accept_changes
    from .models import _safe_dirname
    proj = store.project(pid); ws = Path(proj["root"]); spec = read_spec(proj["spec"])
    m = next((x for x in spec.materials if x.identifier == material), None)
    if m is None:
        raise InputError(f"Unknown material {material!r}")
    info = validate_armor3d_files(ws, material, tuple(m.armor))
    a = ws / "src/main/resources/assets" / pid
    targets = {"geo": a / "geo/item/armor" / f"{material}.geo.json", "anim": a / "animations/item/armor" / f"{material}.animation.json", "png": a / "textures/item/armor" / f"{material}.png"}
    for k, dst in targets.items():
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ws / info["files"][k], dst)
    changed = [str(t.relative_to(ws)).replace("\\", "/") for t in targets.values()]
    history = ws / ".mod-orchestra" / "previews" / _safe_dirname(run_id); history.mkdir(parents=True, exist_ok=True)
    for r in info["renders"]:
        shutil.copyfile(ws / r, history / Path(r).name)
    accepted = accept_changes(ws, run_id=run_id, actor=actor, changed=changed)
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid); _reopen_build(store, pid)
    store.add_event(pid, "controller", "ARMOR3D_INSTALLED", {"material": material, "run": run_id, "task": task_id, "bones": info["bones"], "cubes": info["cubes"]})
    return info | {"installed": changed, "accepted": accepted["accepted"], "previews": [f".mod-orchestra/previews/{_safe_dirname(run_id)}/{Path(r).name}" for r in info["renders"]]}
