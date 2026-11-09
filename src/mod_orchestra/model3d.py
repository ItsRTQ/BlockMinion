"""3D models for items, on demand, one by one ("Make it 3D").

Nothing in the item's code changes. A client entrypoint (`client/Model3DClient`) reads
`assets/<mod>/model3d/index.json` and registers, through Fabric's BuiltinItemRendererRegistry, an `Item3DRenderer` for
every item listed there: in the hand, on the ground, in a frame and in a mob's hand it draws the GeckoLib model
(`geo/item/model3d/<id>.geo.json`, `animations/item/model3d/<id>.animation.json`, `textures/item/model3d/<id>.png`);
in the inventory it keeps drawing the 2D icon (`textures/item/<id>.png`). The item model JSON becomes `builtin/entity`
with the display transforms the icon had (handheld for tools and weapons), because the model is built in the icon's own
16x16x16 space and therefore sits in the hand exactly where the icon did.

The designer (task ITEM3D:<id>) builds the model; on DONE the controller validates and installs it and wires the project
the first time: the support classes are new files; build.gradle / gradle.properties (GeckoLib), fabric.mod.json (the
client entrypoint) and the item model JSON are patched only when the manifest vouches for them, otherwise a coder task
(ITEM3DWIRE) makes exactly those edits.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from .state import Store, StateError
from .validation import InputError

DIR = "models/items3d"
GENERATED = ("SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED")

# Vanilla's item/generated and item/handheld display transforms: the 3D model lives in the icon's space, so it is held like the icon.
_GENERATED = {"ground": {"rotation": [0, 0, 0], "translation": [0, 2, 0], "scale": [0.5, 0.5, 0.5]},
              "head": {"rotation": [0, 180, 0], "translation": [0, 13, 7], "scale": [1, 1, 1]},
              "thirdperson_righthand": {"rotation": [0, 0, 0], "translation": [0, 3, 1], "scale": [0.55, 0.55, 0.55]},
              "firstperson_righthand": {"rotation": [0, -90, 25], "translation": [1.13, 3.2, 1.13], "scale": [0.68, 0.68, 0.68]},
              "fixed": {"rotation": [0, 180, 0], "translation": [0, 0, 0], "scale": [1, 1, 1]}}
_HANDHELD = {**_GENERATED,
             "thirdperson_righthand": {"rotation": [0, -90, 55], "translation": [0, 4.0, 0.5], "scale": [0.85, 0.85, 0.85]},
             "thirdperson_lefthand": {"rotation": [0, 90, -55], "translation": [0, 4.0, 0.5], "scale": [0.85, 0.85, 0.85]},
             "firstperson_righthand": {"rotation": [0, -90, 25], "translation": [1.13, 3.2, 1.13], "scale": [0.68, 0.68, 0.68]},
             "firstperson_lefthand": {"rotation": [0, 90, -25], "translation": [1.13, 3.2, 1.13], "scale": [0.68, 0.68, 0.68]}}
_GUI = {"rotation": [0, 0, 0], "translation": [0, 0, 0], "scale": [1, 1, 1]}   # the renderer draws the 2D icon itself in the inventory


def candidates(spec) -> dict[str, dict]:
    """Items that can get a 3D model: {id: {label, kind, art_kind, art_id, handheld}} (simple items, tools and weapons, foods)."""
    out = {}
    for f in spec.features:
        if f.kind == "item":
            out[f.identifier] = {"label": f.label, "kind": "item", "art_kind": "item", "art_id": f.identifier, "handheld": False}
    for m in spec.materials:
        for k in m.tools:
            out[f"{m.identifier}_{k}"] = {"label": f"{m.label} {k}", "kind": k, "art_kind": "tool", "art_id": f"{m.identifier}_{k}", "handheld": True}
    for fd in spec.foods:
        out[fd.identifier] = {"label": fd.label, "kind": "food", "art_kind": "food", "art_id": fd.identifier, "handheld": False}
    return out


# ------------------------------------------------------------------------------------------------ Java support (new files)

def support_java(package: str) -> dict[str, str]:
    """client/Model3DAnimatable, client/Item3DRenderer, client/Model3DClient: relative to src/main/java/<package>/."""
    p = package
    animatable = "\n".join([
        f"package {p}.client;", "",
        "import software.bernie.geckolib.animatable.GeoAnimatable;", "import software.bernie.geckolib.animatable.instance.AnimatableInstanceCache;",
        "import software.bernie.geckolib.animation.AnimatableManager;", "import software.bernie.geckolib.animation.AnimationController;",
        "import software.bernie.geckolib.animation.RawAnimation;", "import software.bernie.geckolib.util.GeckoLibUtil;", "import software.bernie.geckolib.util.RenderUtil;", "",
        "/** A GeckoLib model with no game object behind it (a 3D item): it only needs a cache and, if it has one, its idle loop. */",
        "public final class Model3DAnimatable implements GeoAnimatable {",
        "    private final AnimatableInstanceCache cache = GeckoLibUtil.createInstanceCache(this);",
        "    private final String id;", "    private final boolean animated;", "",
        "    public Model3DAnimatable(String id, boolean animated) { this.id = id; this.animated = animated; }", "",
        "    @Override",
        "    public void registerControllers(AnimatableManager.ControllerRegistrar controllers) {",
        '        if (animated) controllers.add(new AnimationController<>(this, "idle", 0, state -> state.setAndContinue(RawAnimation.begin().thenLoop("animation." + id + ".idle"))));',
        "    }", "",
        "    @Override", "    public AnimatableInstanceCache getAnimatableInstanceCache() { return cache; }", "",
        "    @Override", "    public double getTick(Object object) { return RenderUtil.getCurrentTick(); }",
        "}", ""])
    renderer = "\n".join([
        f"package {p}.client;", "",
        "import com.mojang.blaze3d.vertex.PoseStack;", "import com.mojang.blaze3d.vertex.VertexConsumer;",
        "import net.fabricmc.fabric.api.client.rendering.v1.BuiltinItemRendererRegistry;",
        "import net.minecraft.client.renderer.MultiBufferSource;", "import net.minecraft.client.renderer.RenderType;",
        "import net.minecraft.resources.ResourceLocation;", "import net.minecraft.world.item.ItemDisplayContext;", "import net.minecraft.world.item.ItemStack;",
        "import software.bernie.geckolib.cache.object.BakedGeoModel;", "import software.bernie.geckolib.model.DefaultedItemGeoModel;",
        "import software.bernie.geckolib.renderer.GeoObjectRenderer;", "",
        "/** Draws an item's 3D model everywhere except the inventory, where its 2D icon stays (readable at slot size). */",
        "public final class Item3DRenderer implements BuiltinItemRendererRegistry.DynamicItemRenderer {",
        "    private final Model3DAnimatable animatable;", "    private final ResourceLocation icon;", "    private final ResourceLocation texture;",
        "    private final GeoObjectRenderer<Model3DAnimatable> renderer;", "",
        "    public Item3DRenderer(String modId, String id, boolean animated) {",
        "        this.animatable = new Model3DAnimatable(id, animated);",
        '        this.icon = ResourceLocation.fromNamespaceAndPath(modId, "textures/item/" + id + ".png");',
        '        this.texture = ResourceLocation.fromNamespaceAndPath(modId, "textures/item/model3d/" + id + ".png");',
        '        this.renderer = new GeoObjectRenderer<>(new DefaultedItemGeoModel<Model3DAnimatable>(ResourceLocation.fromNamespaceAndPath(modId, "model3d/" + id))) {',
        "            @Override",
        "            public void preRender(PoseStack poseStack, Model3DAnimatable a, BakedGeoModel model, MultiBufferSource bufferSource, VertexConsumer buffer,",
        "                                  boolean isReRender, float partialTick, int packedLight, int packedOverlay, int colour) {",
        "                super.preRender(poseStack, a, model, bufferSource, buffer, isReRender, partialTick, packedLight, packedOverlay, colour);",
        "                poseStack.translate(0f, -0.51f, 0f);   // the icon's space: the model's y 0..16 is the icon's 0..1",
        "            }", "        };", "    }", "",
        "    @Override",
        "    public void render(ItemStack stack, ItemDisplayContext mode, PoseStack poseStack, MultiBufferSource buffers, int light, int overlay) {",
        "        if (mode == ItemDisplayContext.GUI) { drawIcon(icon, poseStack, buffers, light, overlay); return; }",
        "        RenderType type = RenderType.entityCutoutNoCull(texture);",
        "        renderer.render(poseStack, animatable, buffers, type, buffers.getBuffer(type), light, 0f);",
        "    }", "",
        "    /** The 2D icon as a flat quad filling the slot (the item JSON's GUI transform is the identity). */",
        "    public static void drawIcon(ResourceLocation icon, PoseStack poseStack, MultiBufferSource buffers, int light, int overlay) {",
        "        VertexConsumer vc = buffers.getBuffer(RenderType.entityCutoutNoCull(icon));",
        "        PoseStack.Pose pose = poseStack.last();",
        "        vertex(vc, pose, 0f, 0f, 0f, 1f, light, overlay); vertex(vc, pose, 1f, 0f, 1f, 1f, light, overlay);",
        "        vertex(vc, pose, 1f, 1f, 1f, 0f, light, overlay); vertex(vc, pose, 0f, 1f, 0f, 0f, light, overlay);",
        "    }", "",
        "    private static void vertex(VertexConsumer vc, PoseStack.Pose pose, float x, float y, float u, float v, int light, int overlay) {",
        "        vc.addVertex(pose, x, y, 0.5f).setColor(255, 255, 255, 255).setUv(u, v).setOverlay(overlay).setLight(light).setNormal(pose, 0f, 0f, 1f);",
        "    }",
        "}", ""])
    client = "\n".join([
        f"package {p}.client;", "",
        f"import {p}.ModMain;",
        "import com.google.gson.JsonElement;", "import com.google.gson.JsonObject;", "import com.google.gson.JsonParser;",
        "import net.fabricmc.api.ClientModInitializer;", "import net.fabricmc.fabric.api.client.rendering.v1.BuiltinItemRendererRegistry;",
        "import net.minecraft.core.registries.BuiltInRegistries;", "import net.minecraft.resources.ResourceLocation;",
        "import net.minecraft.world.item.Item;", "import net.minecraft.world.item.Items;",
        "import java.io.InputStream;", "import java.io.InputStreamReader;", "import java.nio.charset.StandardCharsets;", "",
        "/** Gives every item listed in assets/<mod>/model3d/index.json its 3D renderer. Adding a 3D item later is data, not code. */",
        "public final class Model3DClient implements ClientModInitializer {",
        "    @Override",
        "    public void onInitializeClient() {",
        "        String mod = ModMain.MOD_ID;",
        '        try (InputStream in = Model3DClient.class.getResourceAsStream("/assets/" + mod + "/model3d/index.json")) {',
        "            if (in == null) return;",
        "            JsonObject index = JsonParser.parseReader(new InputStreamReader(in, StandardCharsets.UTF_8)).getAsJsonObject();",
        '            if (!index.has("items")) return;',
        '            for (JsonElement e : index.getAsJsonArray("items")) {',
        "                JsonObject o = e.getAsJsonObject();",
        '                String id = o.get("id").getAsString();',
        '                boolean animated = o.has("animated") && o.get("animated").getAsBoolean();',
        "                Item item = BuiltInRegistries.ITEM.get(ResourceLocation.fromNamespaceAndPath(mod, id));",
        '                if (item == Items.AIR) { ModMain.LOGGER.warn("3D model for an unknown item: {}", id); continue; }',
        "                if (item instanceof software.bernie.geckolib.animatable.GeoItem) continue;   // it draws itself (Item3DGeoRenderer) and plays its actions",
        "                BuiltinItemRendererRegistry.INSTANCE.register(item, new Item3DRenderer(mod, id, animated));",
        "            }",
        "        } catch (Exception e) {",
        '            ModMain.LOGGER.error("Could not read the 3D model index", e);',
        "        }", "    }",
        "}", ""])
    projectile = "\n".join([
        f"package {p}.client;", "",
        "import com.mojang.blaze3d.vertex.PoseStack;", "import com.mojang.blaze3d.vertex.VertexConsumer;", "import com.mojang.math.Axis;",
        "import net.minecraft.client.renderer.MultiBufferSource;", "import net.minecraft.client.renderer.RenderType;",
        "import net.minecraft.client.renderer.entity.EntityRenderer;", "import net.minecraft.client.renderer.entity.EntityRendererProvider;",
        "import net.minecraft.resources.ResourceLocation;", "import net.minecraft.util.Mth;", "import net.minecraft.world.entity.Entity;",
        "import software.bernie.geckolib.cache.object.BakedGeoModel;", "import software.bernie.geckolib.model.DefaultedItemGeoModel;",
        "import software.bernie.geckolib.renderer.GeoObjectRenderer;", "",
        "/** Draws a projectile as a 3D model that points where it flies (like an arrow: the model's nose is +X). */",
        "public class Projectile3DRenderer<T extends Entity> extends EntityRenderer<T> {",
        "    private final Model3DAnimatable animatable;", "    private final ResourceLocation texture;",
        "    private final GeoObjectRenderer<Model3DAnimatable> renderer;", "",
        "    public Projectile3DRenderer(EntityRendererProvider.Context context, String modId, String id) {",
        "        super(context);",
        "        this.animatable = new Model3DAnimatable(id, true);",
        '        this.texture = ResourceLocation.fromNamespaceAndPath(modId, "textures/item/model3d/projectile/" + id + ".png");',
        '        this.renderer = new GeoObjectRenderer<>(new DefaultedItemGeoModel<Model3DAnimatable>(ResourceLocation.fromNamespaceAndPath(modId, "model3d/projectile/" + id))) {',
        "            @Override",
        "            public void preRender(PoseStack poseStack, Model3DAnimatable a, BakedGeoModel model, MultiBufferSource bufferSource, VertexConsumer buffer,",
        "                                  boolean isReRender, float partialTick, int packedLight, int packedOverlay, int colour) {",
        "                super.preRender(poseStack, a, model, bufferSource, buffer, isReRender, partialTick, packedLight, packedOverlay, colour);",
        "                poseStack.translate(-0.5f, -0.51f, -0.5f);   // the model's origin is the projectile's centre",
        "            }", "        };", "    }", "",
        "    @Override",
        "    public void render(T entity, float entityYaw, float partialTick, PoseStack poseStack, MultiBufferSource buffers, int light) {",
        "        poseStack.pushPose();",
        "        poseStack.mulPose(Axis.YP.rotationDegrees(Mth.lerp(partialTick, entity.yRotO, entity.getYRot()) - 90.0F));",
        "        poseStack.mulPose(Axis.ZP.rotationDegrees(Mth.lerp(partialTick, entity.xRotO, entity.getXRot())));",
        "        RenderType type = RenderType.entityCutoutNoCull(texture);",
        "        renderer.render(poseStack, animatable, buffers, type, buffers.getBuffer(type), light, partialTick);",
        "        poseStack.popPose();",
        "        super.render(entity, entityYaw, partialTick, poseStack, buffers, light);",
        "    }", "",
        "    @Override", "    public ResourceLocation getTextureLocation(T entity) { return texture; }",
        "}", ""])
    actions = "\n".join([
        f"package {p}.model3d;", "",
        "import net.minecraft.server.level.ServerLevel;", "import net.minecraft.world.entity.Entity;", "import net.minecraft.world.item.ItemStack;",
        "import software.bernie.geckolib.animatable.GeoItem;", "import software.bernie.geckolib.animatable.SingletonGeoAnimatable;",
        "import software.bernie.geckolib.animation.AnimatableManager;", "import software.bernie.geckolib.animation.AnimationController;",
        "import software.bernie.geckolib.animation.PlayState;", "import software.bernie.geckolib.animation.RawAnimation;", "",
        "/** Actions of a 3D item (use, attack, equip, ...): one-shot animations the item's own code triggers on the server; GeckoLib syncs them. */",
        "public final class Item3DActions {",
        '    public static final String CONTROLLER = "actions";', "",
        "    private Item3DActions() {}", "",
        "    /** Call once from the item's constructor. */",
        "    public static void init(GeoItem item) { SingletonGeoAnimatable.registerSyncedAnimatable(item); }", "",
        "    /** Call from registerControllers: the idle loop (if the model has one) and one triggerable animation per action. */",
        "    public static void controllers(GeoItem item, AnimatableManager.ControllerRegistrar controllers, String id, boolean idle, String... actions) {",
        '        if (idle) controllers.add(new AnimationController<>(item, "idle", 0, state -> state.setAndContinue(RawAnimation.begin().thenLoop("animation." + id + ".idle"))));',
        "        AnimationController<GeoItem> c = new AnimationController<>(item, CONTROLLER, 0, state -> PlayState.STOP);",
        '        for (String a : actions) c.triggerableAnim(a, RawAnimation.begin().thenPlay("animation." + id + "." + a));',
        "        controllers.add(c);", "    }", "",
        "    /** Call on the server when the action happens; does nothing on the client. */",
        "    public static void trigger(GeoItem item, Entity holder, ItemStack stack, String action) {",
        "        if (holder.level() instanceof ServerLevel server) item.triggerAnim(holder, GeoItem.getOrAssignId(stack, server), CONTROLLER, action);",
        "    }",
        "}", ""])
    georenderer = "\n".join([
        f"package {p}.client;", "",
        "import com.mojang.blaze3d.vertex.PoseStack;", "import com.mojang.blaze3d.vertex.VertexConsumer;",
        "import net.minecraft.client.renderer.MultiBufferSource;", "import net.minecraft.resources.ResourceLocation;",
        "import net.minecraft.world.item.Item;", "import net.minecraft.world.item.ItemDisplayContext;", "import net.minecraft.world.item.ItemStack;",
        "import software.bernie.geckolib.animatable.GeoAnimatable;", "import software.bernie.geckolib.cache.object.BakedGeoModel;",
        "import software.bernie.geckolib.model.DefaultedItemGeoModel;", "import software.bernie.geckolib.renderer.GeoItemRenderer;", "",
        "/** The renderer of a 3D item that is a GeoItem (it plays actions): same space and same 2D inventory icon as Item3DRenderer. */",
        "public class Item3DGeoRenderer<T extends Item & GeoAnimatable> extends GeoItemRenderer<T> {",
        "    private final ResourceLocation icon;", "",
        "    public Item3DGeoRenderer(String modId, String id) {",
        '        super(new DefaultedItemGeoModel<T>(ResourceLocation.fromNamespaceAndPath(modId, "model3d/" + id)));',
        '        this.icon = ResourceLocation.fromNamespaceAndPath(modId, "textures/item/" + id + ".png");',
        "    }", "",
        "    @Override",
        "    public void preRender(PoseStack poseStack, T animatable, BakedGeoModel model, MultiBufferSource bufferSource, VertexConsumer buffer,",
        "                          boolean isReRender, float partialTick, int packedLight, int packedOverlay, int colour) {",
        "        super.preRender(poseStack, animatable, model, bufferSource, buffer, isReRender, partialTick, packedLight, packedOverlay, colour);",
        "        if (!isReRender) poseStack.translate(0f, -0.51f, 0f);   // the icon's space, like Item3DRenderer",
        "    }", "",
        "    @Override",
        "    public void renderByItem(ItemStack stack, ItemDisplayContext mode, PoseStack poseStack, MultiBufferSource buffers, int light, int overlay) {",
        "        if (mode == ItemDisplayContext.GUI) { Item3DRenderer.drawIcon(icon, poseStack, buffers, light, overlay); return; }",
        "        super.renderByItem(stack, mode, poseStack, buffers, light, overlay);",
        "    }",
        "}", ""])
    return {"client/Model3DAnimatable.java": animatable, "client/Item3DRenderer.java": renderer, "client/Model3DClient.java": client,
            "client/Projectile3DRenderer.java": projectile, "client/Item3DGeoRenderer.java": georenderer, "model3d/Item3DActions.java": actions}


def item_model_json(mod_id: str, ident: str, handheld: bool) -> dict:
    return {"parent": "builtin/entity", "gui_light": "front", "textures": {"particle": f"{mod_id}:item/{ident}"},
            "display": {**(_HANDHELD if handheld else _GENERATED), "gui": _GUI}}


# ------------------------------------------------------------------------------------------------ designer task

ITEM3D_INSTRUCTIONS = """
## Your job on this task (designer — a 3D model for an item)
Build a GeckoLib model of the item named below; in the game it replaces the flat icon in the hand, on the ground, in item
frames and in a mob's hand (the inventory keeps the icon). Create it with `bbmodel_geckolib_create` as
`models/items3d/<id>.bbmodel` with model identifier `<id>` (or keep editing it if it already exists).
Space: build it inside the icon's own 16x16x16 space and lie it the way the icon lies, seen from the front (north): x from -8
to 8, y from 0 to 16, z from -8 to 8, thickness along z around 0. The game holds it with the icon's transforms, so a shape
that follows the icon's layout sits in the hand where the icon did. Small overhangs are fine; the controller refuses a
model that reaches beyond -12..12 on x and z or -4..24 on y.
Read the icon (`<icon>`) and keep its design, palette and proportions: this is the same object, now with depth.
Texture: paint `models/items3d/<id>.png` with a stdlib script (zlib/struct, no PIL) at the model's texture size and set it
with `bbmodel_geckolib_set_texture`.
Animation, all optional (`bbmodel_geckolib_upsert_animation`): a looping `animation.<id>.idle` only for something that moves
by itself at rest (most held objects do not). Actions: when the user's notes ask the object to animate when something happens
to it, make each one a one-shot animation (loop off) named `animation.<id>.<action>`: `use` when it is used, `attack` when it
hits, `equip` when it is drawn, or a short snake_case name of your own for another moment the notes describe. A coder makes
the item's code play each action at its moment. With no animation at all, export an empty animation file.
Deliverables in `models/items3d/`: `<id>.bbmodel`, `<id>.geo.json` (`bbmodel_geckolib_export_geometry`), `<id>.animation.json`
(`bbmodel_geckolib_export_animations`), `<id>.png`, and at least one render `<id>_render.png` (`bbmodel_render`) that you
looked at and corrected before finishing. Report them in `changed_files`. Never touch `src/`: the controller installs them.
"""


def designer_cost(store: Store) -> dict:
    """What designer runs have cost so far (all projects): the estimate shown before a 3D model is requested."""
    with store.tx() as con:
        rows = con.execute("SELECT cost_usd, duration_s FROM runs WHERE role='designer' AND state='DONE' AND cost_usd IS NOT NULL").fetchall()
    if not rows:
        return {"runs": 0}
    costs = [float(r["cost_usd"]) for r in rows]; mins = [float(r["duration_s"] or 0) / 60 for r in rows]
    return {"runs": len(rows), "avg_usd": round(sum(costs) / len(costs), 2), "max_usd": round(max(costs), 2), "avg_minutes": round(sum(mins) / len(mins), 1)}


def request_item3d(store: Store, pid: str, ident: str, notes: str = "") -> dict:
    """USER-ONLY: ask the designer for a 3D model of one item. Costs a designer run; the UI asks first and shows the estimate."""
    from .art import brief as art_brief
    from .models import theme_block, user_words
    from .spec import read_spec
    proj = store.project(pid)
    if proj["status"] not in GENERATED:
        raise StateError("Generate the project first")
    spec = read_spec(proj["spec"])
    cand = candidates(spec)
    if ident not in cand:
        raise InputError(f"{ident!r} cannot get a 3D model here; these can: {sorted(cand)}")
    c = cand[ident]
    ws = Path(proj["root"]); (ws / DIR).mkdir(parents=True, exist_ok=True)
    icon = f"src/main/resources/assets/{pid}/textures/item/{ident}.png"
    base = f"{pid}:ITEM3D:{ident}"
    n = sum(1 for t in store.tasks(pid) if t["id"] == base or t["id"].startswith(base + ":")) + 1
    task_id = base if n == 1 else f"{base}:{n}"
    lines = [ITEM3D_INSTRUCTIONS.replace("<id>", ident).replace("<icon>", icon), user_words(store, pid, c["label"]), theme_block(store, pid),
             f"\n## The item\n{c['label']} (`{ident}`, {c['kind']}{', held like a tool or weapon' if c['handheld'] else ''})",
             "art direction:\n" + art_brief(spec, c["art_kind"], c["art_id"])]
    if (ws / DIR / f"{ident}.bbmodel").is_file():
        lines.append(f"A model already exists (models/items3d/{ident}.bbmodel): edit it as the notes ask, do not start over.")
    prior = [e["payload"].get("notes", "") for e in store.events(pid, 300) if e["kind"] == "ITEM3D_REQUESTED" and e["payload"].get("item") == ident and e["payload"].get("notes")]
    if notes.strip():
        lines += ["", "## The user's notes for this round (their words)", notes.strip()[:1500]]
    if prior:
        lines += ["", "Earlier notes (apply them too):"] + [f"- {x}" for x in prior[-5:]]
    store.add_task(pid, task_id, "designer", f"3D model for {c['label']}")
    with store.tx() as con:
        con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(lines)))
    store.add_event(pid, "user", "ITEM3D_REQUESTED", {"task": task_id, "item": ident, "notes": notes[:300]})
    return {"task": task_id, "item": ident, "estimate": designer_cost(store), "next": {"action": "dispatch", "payload": {"task": task_id}}}


ITEM_BOUNDS = ((-12, 12), (-4, 24), (-12, 12))
PROJ_BOUNDS = ((-12, 12), (-12, 12), (-12, 12))
PDIR = "models/projectiles3d"


def validate_item3d(ws: Path, ident: str, *, folder: str = DIR, bounds=ITEM_BOUNDS) -> dict:
    root = ws / folder
    files = {k: root / f"{ident}.{ext}" for k, ext in (("bbmodel", "bbmodel"), ("geo", "geo.json"), ("anim", "animation.json"), ("png", "png"))}
    missing = [f.name for f in files.values() if not f.is_file()]
    if missing:
        raise InputError(f"designer deliverables missing in {folder}/: {', '.join(missing)}")
    renders = sorted(root.glob(f"{ident}_render*.png"))
    if not renders:
        raise InputError(f"no render ({folder}/{ident}_render.png): the designer must look at the model before finishing")
    try:
        g = json.loads(files["geo"].read_text(encoding="utf8"))["minecraft:geometry"][0]
        desc, bones = g["description"], g["bones"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise InputError("geo.json is not GeckoLib geometry") from None
    if desc.get("identifier") != f"geometry.{ident}":
        raise InputError(f"geo identifier must be geometry.{ident}, got {desc.get('identifier')!r}")
    cubes = [c for b in bones for c in b.get("cubes") or []]
    if not cubes:
        raise InputError("the model has no cubes")
    lo, hi = [1e9] * 3, [-1e9] * 3
    for c in cubes:
        o, s = c.get("origin") or [0, 0, 0], c.get("size") or [0, 0, 0]
        for i in range(3):
            lo[i] = min(lo[i], o[i]); hi[i] = max(hi[i], o[i] + s[i])
    if any(lo[i] < bounds[i][0] or hi[i] > bounds[i][1] for i in range(3)):
        raise InputError(f"the model reaches {[round(v, 1) for v in lo]}..{[round(v, 1) for v in hi]}: keep it within x {bounds[0]}, y {bounds[1]}, z {bounds[2]}")
    png = files["png"].read_bytes()
    w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    if (desc.get("texture_width"), desc.get("texture_height")) != (w, h):
        raise InputError(f"texture is {w}x{h} but geo declares {desc.get('texture_width')}x{desc.get('texture_height')}")
    try:
        anims = json.loads(files["anim"].read_text(encoding="utf8")).get("animations") or {}
    except ValueError:
        raise InputError("animation.json is not JSON") from None
    idle = anims.get(f"animation.{ident}.idle")
    prefix, actions = f"animation.{ident}.", []
    for name, clip in anims.items():
        short = name[len(prefix):] if name.startswith(prefix) else ""
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", short):
            raise InputError(f"animation {name!r}: name it animation.{ident}.<action> (snake_case), or animation.{ident}.idle for the loop")
        if short == "idle":
            continue
        if clip.get("loop") is True:
            raise InputError(f"action {short!r} loops: an action plays once when it happens (loop off)")
        if clip.get("bones"):
            actions.append(short)
    return {"cubes": len(cubes), "bones": [b["name"] for b in bones], "texture": [w, h], "animated": bool(idle and idle.get("bones")), "actions": sorted(actions),
            "bounds": [lo, hi], "renders": [str(r.relative_to(ws)).replace("\\", "/") for r in renders],
            "files": {k: str(v.relative_to(ws)).replace("\\", "/") for k, v in files.items()}}


# ------------------------------------------------------------------------------------------------ install + wiring

def _known(ws: Path, rel: str) -> bool:
    """The file is exactly what the manifest records (the generator's or an accepted revision): safe to patch."""
    from .fabric import current_hashes
    f = ws / rel
    try:
        manifest = json.loads((ws / ".mod-orchestra/generation-manifest.json").read_text(encoding="utf8"))
    except (OSError, ValueError):
        return False
    return f.is_file() and current_hashes(manifest).get(rel) == hashlib.sha256(f.read_bytes()).hexdigest()


def patch_gradle(gradle: str, props: str) -> tuple[str, str] | None:
    """Add the GeckoLib repository and dependency (as the generator writes them). None when the build file has no plain
    `dependencies {` block to extend."""
    from .geckolib import GECKOLIB_VERSION, gradle_dependency_lines
    if "software.bernie.geckolib" in gradle:
        return gradle, props if "geckolib_version" in props else props.rstrip("\n") + f"\ngeckolib_version={GECKOLIB_VERSION}\n"
    if gradle.count("\ndependencies {") != 1:
        return None
    repo, dep = gradle_dependency_lines()
    gradle = gradle.replace("\ndependencies {", "\nrepositories {\n" + repo + "\n}\n\ndependencies {\n" + dep, 1)
    if "geckolib_version" not in props:
        props = props.rstrip("\n") + f"\ngeckolib_version={GECKOLIB_VERSION}\n"
    return gradle, props


def patch_fabric_mod(text: str, package: str) -> str | None:
    try:
        d = json.loads(text)
    except ValueError:
        return None
    entry = f"{package}.client.Model3DClient"
    eps = d.setdefault("entrypoints", {})
    client = eps.setdefault("client", [])
    if not isinstance(client, list):
        return None
    if entry not in client:
        client.append(entry)
    d.setdefault("depends", {}).setdefault("geckolib", ">=4.7")
    return json.dumps(d, indent=2) + "\n"


def wire(store: Store, pid: str, ident: str, *, handheld: bool, animated: bool, actions: list[str] | None = None) -> dict:
    """Make the project draw this item in 3D. Returns {written: [...], coder: [what could not be patched]}."""
    from .spec import read_spec
    proj = store.project(pid); ws = Path(proj["root"]); spec = read_spec(proj["spec"])
    jdir = f"src/main/java/{spec.package.replace('.', '/')}"
    res = f"src/main/resources"
    written, coder = ensure_support(ws, spec)
    _wire_item(ws, spec, pid, ident, handheld, animated, written, coder, actions or [])
    return {"written": written, "coder": coder}


def ensure_support(ws: Path, spec) -> tuple[list[str], list[str]]:
    """The support classes (new files) and GeckoLib in the build; what cannot be patched is returned for the coder."""
    jdir = f"src/main/java/{spec.package.replace('.', '/')}"
    written, coder = [], []
    for name, src in support_java(spec.package).items():
        rel = f"{jdir}/{name}"
        f = ws / rel
        if not f.is_file():
            f.parent.mkdir(parents=True, exist_ok=True); f.write_text(src, encoding="utf8"); written.append(rel)
        elif f.read_text(encoding="utf8") != src:
            if _known(ws, rel):   # the controller's own earlier version: update it
                f.write_text(src, encoding="utf8"); written.append(rel)
            else:
                coder.append(f"{rel} has edits the controller did not record; make it match the controller's current version, keeping what the edits need:\n{src}")
    gradle, props = ws / "build.gradle", ws / "gradle.properties"
    if "software.bernie.geckolib" not in gradle.read_text(encoding="utf8") or "geckolib_version" not in props.read_text(encoding="utf8"):
        patched = patch_gradle(gradle.read_text(encoding="utf8"), props.read_text(encoding="utf8")) if _known(ws, "build.gradle") and _known(ws, "gradle.properties") else None
        if patched is None:
            coder.append("add GeckoLib to the build exactly like a project with mobs has it (the GeckoLib maven repository, the modImplementation line and geckolib_version in gradle.properties)")
        else:
            gradle.write_text(patched[0], encoding="utf8"); props.write_text(patched[1], encoding="utf8"); written += ["build.gradle", "gradle.properties"]
    return written, coder


def _index(ws: Path, pid: str) -> tuple[Path, dict]:
    f = ws / f"src/main/resources/assets/{pid}/model3d/index.json"
    try:
        return f, json.loads(f.read_text(encoding="utf8")) if f.is_file() else {"items": []}
    except ValueError:
        return f, {"items": []}


def _wire_item(ws: Path, spec, pid: str, ident: str, handheld: bool, animated: bool, written: list, coder: list, actions: list) -> None:
    res = "src/main/resources"
    index_rel = f"{res}/assets/{pid}/model3d/index.json"
    index_f = ws / index_rel
    try:
        index = json.loads(index_f.read_text(encoding="utf8")) if index_f.is_file() else {"items": []}
    except ValueError:
        index = {"items": []}
    index["items"] = [i for i in index.get("items", []) if i.get("id") != ident] + [{"id": ident, "animated": animated, **({"actions": actions} if actions else {})}]
    index_f.parent.mkdir(parents=True, exist_ok=True); index_f.write_text(json.dumps(index, indent=2) + "\n", encoding="utf8"); written.append(index_rel)
    fmj_rel = f"{res}/fabric.mod.json"
    fmj = ws / fmj_rel
    entry = f"{spec.package}.client.Model3DClient"
    if entry not in fmj.read_text(encoding="utf8"):
        patched = patch_fabric_mod(fmj.read_text(encoding="utf8"), spec.package) if _known(ws, fmj_rel) else None
        if patched is None:
            coder.append(f"add \"{entry}\" to the client entrypoints in {fmj_rel} and depend on geckolib >=4.7")
        else:
            fmj.write_text(patched, encoding="utf8"); written.append(fmj_rel)
    model_rel = f"{res}/assets/{pid}/models/item/{ident}.json"
    want = json.dumps(item_model_json(pid, ident, handheld), indent=2) + "\n"
    model_f = ws / model_rel
    if not model_f.is_file() or model_f.read_text(encoding="utf8") != want:
        if not model_f.is_file() or _known(ws, model_rel):
            if model_f.is_file():
                keep = ws / ".mod-orchestra/items3d" / f"{ident}.icon-model.json"
                keep.parent.mkdir(parents=True, exist_ok=True)
                if not keep.is_file():
                    shutil.copyfile(model_f, keep)
            model_f.parent.mkdir(parents=True, exist_ok=True); model_f.write_text(want, encoding="utf8"); written.append(model_rel)
        else:
            coder.append(f"replace {model_rel} with exactly this JSON (the item is drawn by its 3D renderer; the inventory keeps the icon):\n{want}")


def install_item3d(store: Store, pid: str, task_id: str, ident: str, *, run_id: str, actor: str) -> dict:
    from .fabric import accept_changes
    from .models import _safe_dirname
    from .spec import read_spec
    proj = store.project(pid); ws = Path(proj["root"])
    cand = candidates(read_spec(proj["spec"]))
    if ident not in cand:
        raise InputError(f"{ident!r} is not an item of this project")
    info = validate_item3d(ws, ident)
    a = ws / "src/main/resources/assets" / pid
    targets = {"geo": a / "geo/item/model3d" / f"{ident}.geo.json", "anim": a / "animations/item/model3d" / f"{ident}.animation.json",
               "png": a / "textures/item/model3d" / f"{ident}.png"}
    for k, dst in targets.items():
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ws / info["files"][k], dst)
    changed = [str(t.relative_to(ws)).replace("\\", "/") for t in targets.values()]
    wired = wire(store, pid, ident, handheld=cand[ident]["handheld"], animated=info["animated"], actions=info["actions"])
    changed += wired["written"]
    history = ws / ".mod-orchestra" / "previews" / _safe_dirname(run_id); history.mkdir(parents=True, exist_ok=True)
    for r in info["renders"]:
        shutil.copyfile(ws / r, history / Path(r).name)
    for k in ("bbmodel", "geo", "anim", "png"):
        shutil.copyfile(ws / info["files"][k], history / Path(info["files"][k]).name)
    accepted = accept_changes(ws, run_id=run_id, actor=actor, changed=sorted(set(changed)))
    wire_task = None
    if wired["coder"]:
        base = f"{pid}:ITEM3DWIRE:{ident}"
        wire_task = base if not any(t["id"] == base for t in store.tasks(pid)) else f"{base}:{sum(1 for t in store.tasks(pid) if t['id'].startswith(base)) + 1}"
        brief = [f"The item {ident} now has a 3D model (installed under assets/{pid}/geo|animations|textures/item/model3d/). These project files were",
                 "not what the controller last recorded, so it did not touch them. Make exactly these edits and nothing else:"]
        brief += [f"- {x}" for x in wired["coder"]]
        brief += ["Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
        store.add_task(pid, wire_task, "coder", f"Wire the 3D model of {ident}")
        with store.tx() as con:
            con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (wire_task, "\n".join(brief)))
    anim_task = request_actions_wiring(store, pid, ident, info["actions"], info["animated"]) if info["actions"] else None
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid); _reopen_build(store, pid)
    store.add_event(pid, "controller", "ITEM3D_INSTALLED", {"actions": info["actions"], "anim_task": anim_task} |  {"item": ident, "task": task_id, "run": run_id, "cubes": info["cubes"], "animated": info["animated"],
                                                            "wire_task": wire_task})
    return info | {"installed": changed, "accepted": accepted["accepted"], "wire_task": wire_task, "anim_task": anim_task,
                   "previews": [f".mod-orchestra/previews/{_safe_dirname(run_id)}/{Path(r).name}" for r in info["renders"]]}


def actions_brief(package: str, ident: str, actions: list[str], idle: bool) -> list[str]:
    """The coder's recipe: the item becomes a GeoItem that draws itself with Item3DGeoRenderer and plays each action at its moment."""
    names = ", ".join(f'"{a}"' for a in actions)
    code = f"""public class <ItsClass> extends <WhatItExtendsNow> implements GeoItem {{
    private final AnimatableInstanceCache cache = GeckoLibUtil.createInstanceCache(this);

    public <ItsClass>(/* its current arguments */) {{ super(/* ... */); Item3DActions.init(this); }}

    @Override
    public void registerControllers(AnimatableManager.ControllerRegistrar controllers) {{
        Item3DActions.controllers(this, controllers, "{ident}", {str(idle).lower()}, {names});
    }}

    @Override
    public AnimatableInstanceCache getAnimatableInstanceCache() {{ return cache; }}

    @Override
    public void createGeoRenderer(Consumer<GeoRenderProvider> consumer) {{
        consumer.accept(new GeoRenderProvider() {{
            private Item3DGeoRenderer<<ItsClass>> renderer;
            @Override
            public BlockEntityWithoutLevelRenderer getGeoItemRenderer() {{
                if (renderer == null) renderer = new Item3DGeoRenderer<>(ModMain.MOD_ID, "{ident}");
                return renderer;
            }}
        }});
    }}
}}"""
    moments = {"use": f'when it is used (in use(...), or wherever it fires or acts): Item3DActions.trigger(this, player, stack, "use")',
               "attack": f'when it hits (hurtEnemy(...)): Item3DActions.trigger(this, attacker, stack, "attack")',
               "equip": f'when it becomes the selected item (inventoryTick(...) with selected turning true; remember the previous state on the stack): Item3DActions.trigger(this, entity, stack, "equip")'}
    lines = [f"The item `{ident}` has a 3D model with these actions: {', '.join(actions)}. Make its code play them.",
             f"1. Make its item class a GeckoLib GeoItem (helpers already in the project: {package}.model3d.Item3DActions, {package}.client.Item3DGeoRenderer).",
             "   If it is registered as a plain vanilla class (new Item(...), new SwordItem(...) in ModMain), create a class for it that extends that same",
             "   class, keep every property and argument, and register that class instead. The shape (fill in the class names):", code,
             "   Imports: software.bernie.geckolib.animatable.GeoItem, .animatable.client.GeoRenderProvider, .animatable.instance.AnimatableInstanceCache,",
             "   .animation.AnimatableManager, .util.GeckoLibUtil; net.minecraft.client.renderer.BlockEntityWithoutLevelRenderer; java.util.function.Consumer.",
             "2. Trigger each action at its moment (on the server; the helper does nothing on the client):"]
    lines += [f"   - {a}: " + moments.get(a, f'at the moment its name describes, if the item has such a moment: Item3DActions.trigger(this, holder, stack, "{a}")') for a in actions]
    lines += ["3. Do not touch the model files or assets/<mod>/model3d/index.json: a GeoItem draws itself, and the 3D index skips it.",
              "Change nothing else. Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
    return lines


def request_actions_wiring(store: Store, pid: str, ident: str, actions: list[str], idle: bool) -> str:
    from .spec import read_spec
    spec = read_spec(store.project(pid)["spec"])
    base = f"{pid}:ITEM3DANIM:{ident}"
    tasks = [t for t in store.tasks(pid) if t["id"] == base or t["id"].startswith(base + ":")]
    waiting = next((t for t in tasks if t["state"] in ("BACKLOG", "READY")), None)
    task_id = waiting["id"] if waiting else (base if not tasks else f"{base}:{len(tasks) + 1}")
    if waiting is None:
        store.add_task(pid, task_id, "coder", f"Play the actions of the 3D {ident}")
    with store.tx() as con:
        con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(actions_brief(spec.package, ident, actions, idle))))
    return task_id


def items3d(ws: Path, pid: str) -> set[str]:
    """Items the project currently draws in 3D (its index)."""
    try:
        return {i["id"] for i in json.loads((ws / f"src/main/resources/assets/{pid}/model3d/index.json").read_text(encoding="utf8")).get("items", [])}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


# ------------------------------------------------------------------------------------------------ projectiles

PROJ3D_INSTRUCTIONS = """
## Your job on this task (designer — a 3D model for a projectile)
A projectile of this mod flies as a flat sprite today. Build a GeckoLib model of it: create `models/projectiles3d/<id>.bbmodel`
with `bbmodel_geckolib_create` (model identifier `<id>`), or keep editing it if it already exists.
Orientation: the projectile flies toward +X. Put its front (the leading end) on +X and centre it on the origin; the game turns
it to follow its flight, nose first. Keep it within -12..12 on every axis (a projectile is small: compare with the sprite).
Read the sprite it replaces (`<sprite>`) and keep its colours and character: this is the same thing, now with depth.
Texture: paint `models/projectiles3d/<id>.png` with a stdlib script (zlib/struct, no PIL) at the model's texture size and set it
with `bbmodel_geckolib_set_texture`. A looping `animation.<id>.idle` is optional, if it should move in flight; without one export
an empty animation file.
Deliverables in `models/projectiles3d/`: `<id>.bbmodel`, `<id>.geo.json`, `<id>.animation.json`, `<id>.png`, and at least one render
`<id>_render.png` that you looked at and corrected. Report them in `changed_files`. Never touch `src/`.
"""


def projectile_assets(store: Store, pid: str) -> dict[str, dict]:
    """The projectiles the coder gave their own art (ART_REQUESTED, kind projectile): {id: {card, path, what, for, model3d}}."""
    ws = Path(store.project(pid)["root"])
    _, index = _index(ws, pid)
    done = set(index.get("projectiles", []))
    out = {}
    for e in reversed(store.events(pid, 500)):
        if e["kind"] != "ART_REQUESTED":
            continue
        for a in e["payload"].get("assets", []):
            if a.get("kind") == "projectile":
                out[a["id"]] = {"card": e["payload"].get("card"), "path": a["path"], "what": a["what"], "for": a.get("for", []), "model3d": a["id"] in done}
    return out


def request_proj3d(store: Store, pid: str, ident: str, notes: str = "") -> dict:
    """USER-ONLY: a 3D model for a projectile the coder made (designer, then a coder touch-up that switches its renderer)."""
    from .art import brief as art_brief
    from .artreq import _owner_kind
    from .models import theme_block, user_words
    from .spec import read_spec
    proj = store.project(pid)
    if proj["status"] not in GENERATED:
        raise StateError("Generate the project first")
    assets = projectile_assets(store, pid)
    if ident not in assets:
        raise InputError(f"{ident!r} is not a projectile with its own art; these are: {sorted(assets) or 'none yet (give the feature its own art first)'}")
    a = assets[ident]; spec = read_spec(proj["spec"])
    ws = Path(proj["root"]); (ws / PDIR).mkdir(parents=True, exist_ok=True)
    base = f"{pid}:PROJ3D:{ident}"
    n = sum(1 for t in store.tasks(pid) if t["id"] == base or t["id"].startswith(base + ":")) + 1
    task_id = base if n == 1 else f"{base}:{n}"
    lines = [PROJ3D_INSTRUCTIONS.replace("<id>", ident).replace("<sprite>", a["path"]), user_words(store, pid), theme_block(store, pid),
             f"\n## The projectile\n{ident}: {a['what']}"]
    for owner in a["for"]:
        kind = _owner_kind(spec, owner)
        if kind:
            lines.append(f"it belongs to {owner} ({kind}); its art direction:\n" + art_brief(spec, kind, owner))
    if (ws / PDIR / f"{ident}.bbmodel").is_file():
        lines.append(f"A model already exists (models/projectiles3d/{ident}.bbmodel): edit it as the notes ask, do not start over.")
    if notes.strip():
        lines += ["", "## The user's notes for this round (their words)", notes.strip()[:1500]]
    store.add_task(pid, task_id, "designer", f"3D model for the projectile {ident}")
    with store.tx() as con:
        con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(lines)))
    store.add_event(pid, "user", "PROJ3D_REQUESTED", {"task": task_id, "projectile": ident, "notes": notes[:300]})
    return {"task": task_id, "projectile": ident, "estimate": designer_cost(store), "next": {"action": "dispatch", "payload": {"task": task_id}}}


def install_proj3d(store: Store, pid: str, task_id: str, ident: str, *, run_id: str, actor: str) -> dict:
    """Install the designer's projectile model and queue the coder's touch-up: the projectile's renderer becomes Projectile3DRenderer."""
    from .fabric import accept_changes
    from .models import _safe_dirname
    from .spec import read_spec
    proj = store.project(pid); ws = Path(proj["root"]); spec = read_spec(proj["spec"])
    assets = projectile_assets(store, pid)
    if ident not in assets:
        raise InputError(f"{ident!r} is not a projectile of this project")
    info = validate_item3d(ws, ident, folder=PDIR, bounds=PROJ_BOUNDS)
    a = ws / "src/main/resources/assets" / pid
    targets = {"geo": a / "geo/item/model3d/projectile" / f"{ident}.geo.json", "anim": a / "animations/item/model3d/projectile" / f"{ident}.animation.json",
               "png": a / "textures/item/model3d/projectile" / f"{ident}.png"}
    for k, dst in targets.items():
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ws / info["files"][k], dst)
    changed = [str(t.relative_to(ws)).replace("\\", "/") for t in targets.values()]
    written, coder = ensure_support(ws, spec)
    index_f, index = _index(ws, pid)
    index["projectiles"] = sorted(set(index.get("projectiles", [])) | {ident})
    index_f.parent.mkdir(parents=True, exist_ok=True); index_f.write_text(json.dumps(index, indent=2) + "\n", encoding="utf8")
    changed += written + [str(index_f.relative_to(ws)).replace("\\", "/")]
    history = ws / ".mod-orchestra" / "previews" / _safe_dirname(run_id); history.mkdir(parents=True, exist_ok=True)
    for r in info["renders"]:
        shutil.copyfile(ws / r, history / Path(r).name)
    accepted = accept_changes(ws, run_id=run_id, actor=actor, changed=sorted(set(changed)))
    base = f"{pid}:PROJ3DWIRE:{ident}"
    wire_task = base if not any(t["id"] == base for t in store.tasks(pid)) else f"{base}:{sum(1 for t in store.tasks(pid) if t['id'].startswith(base)) + 1}"
    brief = [f"The projectile that flies as the sprite {assets[ident]['path']} ({assets[ident]['what']}) now has a 3D model, installed at",
             f"assets/{pid}/geo|animations|textures/item/model3d/projectile/{ident}. Switch that projectile's renderer, where it is registered on the",
             f"client, to `ctx -> new Projectile3DRenderer<>(ctx, ModMain.MOD_ID, \"{ident}\")` (class {spec.package}.client.Projectile3DRenderer, already in",
             "the project). It points the model along the projectile's yaw and pitch like an arrow: make sure the entity keeps its rotation following",
             "its motion every tick (Projectile.updateRotation(), or setting yRot/xRot from the velocity). Keep its item and sprite: they are still its icon.",
             "Change nothing else."]
    brief += [f"- also: {x}" for x in coder]
    brief += ["Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
    store.add_task(pid, wire_task, "coder", f"Fly the 3D model of {ident}")
    with store.tx() as con:
        con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (wire_task, "\n".join(brief)))
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid); _reopen_build(store, pid)
    store.add_event(pid, "controller", "PROJ3D_INSTALLED", {"projectile": ident, "task": task_id, "run": run_id, "wire_task": wire_task, "cubes": info["cubes"]})
    return info | {"installed": changed, "accepted": accepted["accepted"], "wire_task": wire_task}
