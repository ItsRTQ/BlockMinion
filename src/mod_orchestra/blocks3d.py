"""3D (and animated) blocks, on demand: a block drawn by a GeckoLib model through a block entity.

A plain Block cannot carry a GeckoLib model; it needs a block entity and must stop drawing its cube. The only code line that
changes is the block's registration in ModMain (`new Block(` -> `new <pkg>.model3d.Block3DBlock(`, patched when the
manifest vouches for ModMain, otherwise by the coder). Everything else is data plus generated classes:
`Block3DInit` (a main entrypoint) reads `assets/<mod>/model3d/index.json` "blocks" and registers one block entity type per
listed Block3DBlock; `Block3DClient` registers a `Block3DRenderer` (GeoBlockRenderer, model `geo/block/model3d/<id>`) for
each; `Block3DEntity` plays the idle loop and the actions (`Block3DEntity.trigger/stop(level, pos, action)`, on the server;
GeckoLib syncs). Block3DBlock turns occlusion off (the model need not fill the cube) and otherwise behaves like the Block.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from .state import Store, StateError
from .validation import InputError

BDIR = "models/blocks3d"
BOUNDS = ((-12, 12), (0, 24), (-12, 12))


def candidates(spec) -> dict[str, dict]:
    return {f.identifier: {"label": f.label} for f in spec.features if f.kind == "block"}


def _index(ws: Path, pid: str) -> tuple[Path, dict]:
    from .model3d import _index as idx
    return idx(ws, pid)


def blocks3d(ws: Path, pid: str) -> set[str]:
    _, index = _index(ws, pid)
    return {b["id"] for b in index.get("blocks", []) if isinstance(b, dict) and b.get("id")}


# ------------------------------------------------------------------------------------------------ Java

def support_java(package: str) -> dict[str, str]:
    p = package
    block = "\n".join([
        f"package {p}.model3d;", "",
        "import net.minecraft.core.BlockPos;", "import net.minecraft.world.level.block.Block;", "import net.minecraft.world.level.block.EntityBlock;",
        "import net.minecraft.world.level.block.RenderShape;", "import net.minecraft.world.level.block.entity.BlockEntity;",
        "import net.minecraft.world.level.block.state.BlockState;", "import org.jetbrains.annotations.Nullable;", "",
        "/** A block drawn by its GeckoLib model (Block3DEntity) instead of its cube; otherwise it behaves like the Block it replaces. */",
        "public class Block3DBlock extends Block implements EntityBlock {",
        "    public Block3DBlock(Properties properties) { super(properties.noOcclusion()); }   // the model need not fill the cube", "",
        "    @Override", "    protected RenderShape getRenderShape(BlockState state) { return RenderShape.ENTITYBLOCK_ANIMATED; }", "",
        "    @Nullable", "    @Override",
        "    public BlockEntity newBlockEntity(BlockPos pos, BlockState state) {",
        "        return Block3DEntity.TYPES.containsKey(state.getBlock()) ? new Block3DEntity(pos, state) : null;",
        "    }",
        "}", ""])
    entity = "\n".join([
        f"package {p}.model3d;", "",
        "import net.minecraft.core.BlockPos;", "import net.minecraft.world.level.Level;", "import net.minecraft.world.level.block.Block;",
        "import net.minecraft.world.level.block.entity.BlockEntity;", "import net.minecraft.world.level.block.entity.BlockEntityType;",
        "import net.minecraft.world.level.block.state.BlockState;",
        "import software.bernie.geckolib.animatable.GeoBlockEntity;", "import software.bernie.geckolib.animatable.instance.AnimatableInstanceCache;",
        "import software.bernie.geckolib.animation.AnimatableManager;", "import software.bernie.geckolib.animation.AnimationController;",
        "import software.bernie.geckolib.animation.PlayState;", "import software.bernie.geckolib.animation.RawAnimation;", "import software.bernie.geckolib.util.GeckoLibUtil;",
        "import java.util.HashMap;", "import java.util.Map;", "",
        "/** The block entity of a 3D block: its idle loop and its actions. Types are registered by Block3DInit from the 3D index. */",
        "public class Block3DEntity extends BlockEntity implements GeoBlockEntity {",
        "    public static final Map<Block, BlockEntityType<Block3DEntity>> TYPES = new HashMap<>();",
        "    private final AnimatableInstanceCache cache = GeckoLibUtil.createInstanceCache(this);", "",
        "    public Block3DEntity(BlockPos pos, BlockState state) { super(TYPES.get(state.getBlock()), pos, state); }", "",
        "    @Override",
        "    public void registerControllers(AnimatableManager.ControllerRegistrar controllers) {",
        "        Block3DInit.Spec s = Block3DInit.SPECS.get(getBlockState().getBlock());",
        "        if (s == null) return;",
        '        if (s.idle()) controllers.add(new AnimationController<>(this, "idle", 0, state -> state.setAndContinue(RawAnimation.begin().thenLoop("animation." + s.id() + ".idle"))));',
        '        AnimationController<Block3DEntity> c = new AnimationController<>(this, "actions", 0, state -> PlayState.STOP);',
        '        for (String a : s.actions()) c.triggerableAnim(a, RawAnimation.begin().thenPlay("animation." + s.id() + "." + a));   // loops if its clip loops',
        "        controllers.add(c);", "    }", "",
        "    @Override", "    public AnimatableInstanceCache getAnimatableInstanceCache() { return cache; }", "",
        "    /** Call on the server when the action happens to the block at pos. */",
        "    public static void trigger(Level level, BlockPos pos, String action) {",
        '        if (!level.isClientSide() && level.getBlockEntity(pos) instanceof Block3DEntity be) be.triggerAnim("actions", action);',
        "    }", "",
        "    /** Call on the server when a looping action ends. */",
        "    public static void stop(Level level, BlockPos pos, String action) {",
        '        if (!level.isClientSide() && level.getBlockEntity(pos) instanceof Block3DEntity be) be.stopTriggeredAnim("actions", action);',
        "    }",
        "}", ""])
    init = "\n".join([
        f"package {p}.model3d;", "",
        f"import {p}.ModMain;",
        "import com.google.gson.JsonElement;", "import com.google.gson.JsonObject;", "import com.google.gson.JsonParser;",
        "import net.fabricmc.api.ModInitializer;", "import net.minecraft.core.Registry;", "import net.minecraft.core.registries.BuiltInRegistries;",
        "import net.minecraft.resources.ResourceLocation;", "import net.minecraft.world.level.block.Block;", "import net.minecraft.world.level.block.entity.BlockEntityType;",
        "import java.io.InputStream;", "import java.io.InputStreamReader;", "import java.nio.charset.StandardCharsets;",
        "import java.util.ArrayList;", "import java.util.HashMap;", "import java.util.List;", "import java.util.Map;", "",
        "/** Registers a block entity type for every 3D block listed in assets/<mod>/model3d/index.json. Adding a 3D block later is data. */",
        "public final class Block3DInit implements ModInitializer {",
        "    public record Spec(String id, boolean idle, List<String> actions) {}",
        "    public static final Map<Block, Spec> SPECS = new HashMap<>();", "",
        "    @Override",
        "    public void onInitialize() {",
        "        String mod = ModMain.MOD_ID;",
        '        try (InputStream in = Block3DInit.class.getResourceAsStream("/assets/" + mod + "/model3d/index.json")) {',
        "            if (in == null) return;",
        "            JsonObject index = JsonParser.parseReader(new InputStreamReader(in, StandardCharsets.UTF_8)).getAsJsonObject();",
        '            if (!index.has("blocks")) return;',
        '            for (JsonElement e : index.getAsJsonArray("blocks")) {',
        "                JsonObject o = e.getAsJsonObject();",
        '                String id = o.get("id").getAsString();',
        "                Block block = BuiltInRegistries.BLOCK.get(ResourceLocation.fromNamespaceAndPath(mod, id));",
        '                if (!(block instanceof Block3DBlock)) { ModMain.LOGGER.warn("3D model for {} but it is not a Block3DBlock", id); continue; }',
        "                List<String> actions = new ArrayList<>();",
        '                if (o.has("actions")) for (JsonElement a : o.getAsJsonArray("actions")) actions.add(a.getAsString());',
        '                SPECS.put(block, new Spec(id, o.has("idle") && o.get("idle").getAsBoolean(), actions));',
        "                BlockEntityType<Block3DEntity> type = Registry.register(BuiltInRegistries.BLOCK_ENTITY_TYPE,",
        '                    ResourceLocation.fromNamespaceAndPath(mod, id + "_3d"), BlockEntityType.Builder.of(Block3DEntity::new, block).build(null));',
        "                Block3DEntity.TYPES.put(block, type);",
        "            }",
        "        } catch (Exception e) {",
        '            ModMain.LOGGER.error("Could not read the 3D model index", e);',
        "        }", "    }",
        "}", ""])
    renderer = "\n".join([
        f"package {p}.client;", "",
        f"import {p}.model3d.Block3DEntity;", "import net.minecraft.resources.ResourceLocation;",
        "import software.bernie.geckolib.model.DefaultedBlockGeoModel;", "import software.bernie.geckolib.renderer.GeoBlockRenderer;", "",
        "/** Draws a 3D block from geo/block/model3d/<id>.geo.json (the block's space: x -8..8, y 0..16, z -8..8). */",
        "public class Block3DRenderer extends GeoBlockRenderer<Block3DEntity> {",
        "    public Block3DRenderer(String modId, String id) {",
        '        super(new DefaultedBlockGeoModel<Block3DEntity>(ResourceLocation.fromNamespaceAndPath(modId, "model3d/" + id)));',
        "    }",
        "}", ""])
    client = "\n".join([
        f"package {p}.client;", "",
        f"import {p}.ModMain;", f"import {p}.model3d.Block3DEntity;", f"import {p}.model3d.Block3DInit;",
        "import net.fabricmc.api.ClientModInitializer;", "import net.minecraft.client.renderer.blockentity.BlockEntityRenderers;", "",
        "/** A renderer for every 3D block Block3DInit registered (main entrypoints run before client ones). */",
        "public final class Block3DClient implements ClientModInitializer {",
        "    @Override",
        "    public void onInitializeClient() {",
        "        Block3DEntity.TYPES.forEach((block, type) -> {",
        "            String id = Block3DInit.SPECS.get(block).id();",
        "            BlockEntityRenderers.register(type, ctx -> new Block3DRenderer(ModMain.MOD_ID, id));",
        "        });",
        "    }",
        "}", ""])
    return {"model3d/Block3DBlock.java": block, "model3d/Block3DEntity.java": entity, "model3d/Block3DInit.java": init,
            "client/Block3DRenderer.java": renderer, "client/Block3DClient.java": client}


def patch_main(java: str, ident: str, package: str) -> str | None:
    """`new Block(` -> `new <pkg>.model3d.Block3DBlock(` on the block's own registration line; None unless exactly one such line."""
    pat = re.compile(r'(Registry\.register\(BuiltInRegistries\.BLOCK,\s*id\("' + re.escape(ident) + r'"\),\s*)new Block\(')
    if f'id("{ident}"), new {package}.model3d.Block3DBlock(' in java:
        return java
    if len(pat.findall(java)) != 1:
        return None
    return pat.sub(lambda m: m.group(1) + f"new {package}.model3d.Block3DBlock(", java, count=1)


def patch_fabric_mod(text: str, package: str) -> str | None:
    try:
        d = json.loads(text)
    except ValueError:
        return None
    eps = d.setdefault("entrypoints", {})
    for key, entry in (("main", f"{package}.model3d.Block3DInit"), ("client", f"{package}.client.Block3DClient")):
        lst = eps.setdefault(key, [])
        if not isinstance(lst, list):
            return None
        if entry not in lst:
            lst.append(entry)
    d.setdefault("depends", {}).setdefault("geckolib", ">=4.7")
    return json.dumps(d, indent=2) + "\n"


def wire(store: Store, pid: str, ident: str, *, idle: bool, actions: list[str]) -> tuple[list[str], list[str]]:
    from . import model3d
    from .spec import read_spec
    proj = store.project(pid); ws = Path(proj["root"]); spec = read_spec(proj["spec"])
    written, coder = model3d.ensure_support(ws, spec)   # GeckoLib in the build (and the item classes, harmless)
    jdir = f"src/main/java/{spec.package.replace('.', '/')}"
    for name, src in support_java(spec.package).items():
        rel = f"{jdir}/{name}"; f = ws / rel
        if not f.is_file():
            f.parent.mkdir(parents=True, exist_ok=True); f.write_text(src, encoding="utf8"); written.append(rel)
        elif f.read_text(encoding="utf8") != src:
            if model3d._known(ws, rel):
                f.write_text(src, encoding="utf8"); written.append(rel)
            else:
                coder.append(f"{rel} has edits the controller did not record; make it match its current version, keeping what the edits need:\n{src}")
    index_f, index = _index(ws, pid)
    index["blocks"] = [b for b in index.get("blocks", []) if b.get("id") != ident] + [{"id": ident, "idle": idle, **({"actions": actions} if actions else {})}]
    index_f.parent.mkdir(parents=True, exist_ok=True); index_f.write_text(json.dumps(index, indent=2) + "\n", encoding="utf8")
    written.append(str(index_f.relative_to(ws)).replace("\\", "/"))
    fmj_rel = "src/main/resources/fabric.mod.json"; fmj = ws / fmj_rel
    if f"{spec.package}.model3d.Block3DInit" not in fmj.read_text(encoding="utf8") or f"{spec.package}.client.Block3DClient" not in fmj.read_text(encoding="utf8"):
        patched = patch_fabric_mod(fmj.read_text(encoding="utf8"), spec.package) if model3d._known(ws, fmj_rel) else None
        if patched is None:
            coder.append(f"in {fmj_rel}: add \"{spec.package}.model3d.Block3DInit\" to the main entrypoints and \"{spec.package}.client.Block3DClient\" to the client ones (after the existing ones)")
        else:
            fmj.write_text(patched, encoding="utf8"); written.append(fmj_rel)
    main_rel = f"{jdir}/ModMain.java"; main = ws / main_rel
    text = main.read_text(encoding="utf8") if main.is_file() else ""
    patched = patch_main(text, ident, spec.package) if model3d._known(ws, main_rel) else None
    if patched is None:
        coder.append(f"register the block {ident} as `new {spec.package}.model3d.Block3DBlock(<the same properties>)` instead of `new Block(...)` "
                     "(keep its id, properties and block item); if it already has its own class, make that class extend Block3DBlock")
    elif patched != text:
        main.write_text(patched, encoding="utf8"); written.append(main_rel)
    return written, coder


# ------------------------------------------------------------------------------------------------ designer task + install

BLOCK3D_INSTRUCTIONS = """
## Your job on this task (designer — a 3D model for a block)
Build a GeckoLib model of the block named below; in the world it replaces the block's cube (its item in the inventory keeps
the block's icon). Create it with `bbmodel_geckolib_create` as `models/blocks3d/<id>.bbmodel` with model identifier `<id>`
(or keep editing it if it already exists).
Space: the block's own space, x from -8 to 8, y from 0 (the floor it stands on) to 16, z from -8 to 8, its front facing north
(-z). It may be smaller than the cube; the controller refuses a model beyond x/z -12..12 or y 0..24.
Read the block's texture (`<texture>`) and keep its palette and character.
Texture: paint `models/blocks3d/<id>.png` with a stdlib script (zlib/struct, no PIL) at the model's texture size and set it with
`bbmodel_geckolib_set_texture`. Animation, all optional: a looping `animation.<id>.idle` only for something that moves by itself;
actions the user's notes ask for as `animation.<id>.<action>` (loop off when it happens once, on when it lasts). With none,
export an empty animation file.
Deliverables in `models/blocks3d/`: `<id>.bbmodel`, `<id>.geo.json`, `<id>.animation.json`, `<id>.png`, and at least one render
`<id>_render.png` that you looked at and corrected. Report them in `changed_files`. Never touch `src/`.
"""


def request_block3d(store: Store, pid: str, ident: str, notes: str = "") -> dict:
    """USER-ONLY: a 3D model for one block (a designer run; the UI shows the cost estimate first)."""
    from .art import brief as art_brief
    from .model3d import GENERATED, designer_cost
    from .models import theme_block, user_words
    from .spec import read_spec
    proj = store.project(pid)
    if proj["status"] not in GENERATED:
        raise StateError("Generate the project first")
    spec = read_spec(proj["spec"])
    cand = candidates(spec)
    if ident not in cand:
        raise InputError(f"{ident!r} is not a block of this project; blocks: {sorted(cand)}")
    ws = Path(proj["root"]); (ws / BDIR).mkdir(parents=True, exist_ok=True)
    base = f"{pid}:BLOCK3D:{ident}"
    n = sum(1 for t in store.tasks(pid) if t["id"] == base or t["id"].startswith(base + ":")) + 1
    task_id = base if n == 1 else f"{base}:{n}"
    lines = [BLOCK3D_INSTRUCTIONS.replace("<id>", ident).replace("<texture>", f"src/main/resources/assets/{pid}/textures/block/{ident}.png"),
             user_words(store, pid, cand[ident]["label"]), theme_block(store, pid),
             f"\n## The block\n{cand[ident]['label']} (`{ident}`)", "art direction:\n" + art_brief(spec, "block", ident)]
    if (ws / BDIR / f"{ident}.bbmodel").is_file():
        lines.append(f"A model already exists (models/blocks3d/{ident}.bbmodel): edit it as the notes ask, do not start over.")
    if notes.strip():
        lines += ["", "## The user's notes for this round (their words)", notes.strip()[:1500]]
    store.add_task(pid, task_id, "designer", f"3D model for {cand[ident]['label']}")
    with store.tx() as con:
        con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (task_id, "\n".join(lines)))
    store.add_event(pid, "user", "BLOCK3D_REQUESTED", {"task": task_id, "block": ident, "notes": notes[:300]})
    return {"task": task_id, "block": ident, "estimate": designer_cost(store), "next": {"action": "dispatch", "payload": {"task": task_id}}}


def actions_brief(package: str, ident: str, actions: list[str], whens: dict, loops: set) -> list[str]:
    lines = [f"The 3D block `{ident}` has these actions: {', '.join(actions)}. Make the block's code play each at its moment, on the server:",
             f"`{package}.model3d.Block3DEntity.trigger(level, pos, \"<action>\")` (and `Block3DEntity.stop(...)` where a looping action ends).",
             f"Where the moment is an interaction with the block (using it, stepping on it, a neighbour update), give it its own class that extends",
             f"{package}.model3d.Block3DBlock, put the call in the matching override, and register that class for `{ident}` (same properties)."]
    for a in actions:
        when = whens.get(a)
        lines.append(f"   - {a}{' (loops)' if a in loops else ''}: " + (f"the user says it plays {when}" if when else "at the moment its name describes"))
    lines += ["Do not touch the model files or assets/<mod>/model3d/index.json. Change nothing else.",
              "Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
    return lines


def install_block3d(store: Store, pid: str, task_id: str, ident: str, *, run_id: str, actor: str) -> dict:
    from .animate import whens as _whens
    from .fabric import accept_changes
    from .model3d import validate_item3d
    from .models import _safe_dirname
    from .spec import read_spec
    proj = store.project(pid); ws = Path(proj["root"]); spec = read_spec(proj["spec"])
    if ident not in candidates(spec):
        raise InputError(f"{ident!r} is not a block of this project")
    info = validate_item3d(ws, ident, folder=BDIR, bounds=BOUNDS)
    a = ws / "src/main/resources/assets" / pid
    targets = {"geo": a / "geo/block/model3d" / f"{ident}.geo.json", "anim": a / "animations/block/model3d" / f"{ident}.animation.json",
               "png": a / "textures/block/model3d" / f"{ident}.png"}
    for k, dst in targets.items():
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ws / info["files"][k], dst)
    changed = [str(t.relative_to(ws)).replace("\\", "/") for t in targets.values()]
    written, coder = wire(store, pid, ident, idle=info["animated"], actions=info["actions"])
    changed += written
    history = ws / ".mod-orchestra" / "previews" / _safe_dirname(run_id); history.mkdir(parents=True, exist_ok=True)
    for r in info["renders"]:
        shutil.copyfile(ws / r, history / Path(r).name)
    accepted = accept_changes(ws, run_id=run_id, actor=actor, changed=sorted(set(changed)))
    tasks = {t["id"]: t for t in store.tasks(pid)}
    wire_task = anim_task = None
    if coder:
        base = f"{pid}:BLOCK3DWIRE:{ident}"
        wire_task = base if base not in tasks else f"{base}:{sum(1 for t in tasks if t.startswith(base)) + 1}"
        store.add_task(pid, wire_task, "coder", f"Wire the 3D model of {ident}")
        brief = [f"The block {ident} now has a 3D model (assets/{pid}/geo|animations|textures/block/model3d/). These edits could not be made by the",
                 "controller because the files have edits it did not record. Make exactly these and nothing else:"] + [f"- {x}" for x in coder]
        brief += ["Run ./gradlew build (or gradlew.bat build) and report BUILD_PASS only if it exits 0."]
        with store.tx() as con:
            con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (wire_task, "\n".join(brief)))
    if info["actions"]:
        whens = _whens(store, pid, "block", ident)
        text = "\n".join(actions_brief(spec.package, ident, info["actions"], whens, set(info["loops"])))
        base = f"{pid}:BLOCKANIM:{ident}"
        waiting = next((t for t in tasks.values() if (t["id"] == base or t["id"].startswith(base + ":")) and t["state"] in ("BACKLOG", "READY")), None)
        anim_task = waiting["id"] if waiting else (base if base not in tasks else f"{base}:{sum(1 for t in tasks if t.startswith(base)) + 1}")
        if waiting is None:
            store.add_task(pid, anim_task, "coder", f"Play the actions of the 3D block {ident}", after=[wire_task] if wire_task else None)
        with store.tx() as con:
            con.execute("INSERT OR REPLACE INTO task_instructions(task_id, text) VALUES(?,?)", (anim_task, text))
    from .dispatch import _source_changed, _reopen_build
    _source_changed(store, pid); _reopen_build(store, pid)
    store.add_event(pid, "controller", "BLOCK3D_INSTALLED", {"block": ident, "task": task_id, "run": run_id, "cubes": info["cubes"],
                                                             "actions": info["actions"], "wire_task": wire_task, "anim_task": anim_task})
    return info | {"installed": changed, "accepted": accepted["accepted"], "wire_task": wire_task, "anim_task": anim_task}
