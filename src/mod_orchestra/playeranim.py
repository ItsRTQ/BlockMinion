"""Player body animations through Player Animation Library (PAL 1.1.6+mc.1.21.1, Fabric).

Minecraft's player model is not a GeckoLib model; PAL hooks the player renderer: it copies the vanilla pose into its bones,
evaluates layered animations and writes the result back. Animations live in `assets/<mod>/player_animations/*.json`
(GeckoLib-style JSON); an animation's id is `<mod>:<its key in the file>`, not the file name.

Here a player animation belongs to an action of a 3D item ("reload": the AK drops its magazine, the player's arms swap it).
The designer animates it on a player rig built with PAL's bone names and pivots (`resources/blockbench/player_rig.*`),
clip key `<item>_<action>`; the controller installs `models/player/player.animation.json` as
`assets/<mod>/player_animations/player.json`. The server says when to play: `PlayerAnims.play(player, "<item>_<action>")`
sends a payload to that player and everyone tracking them; `PlayerAnimsClient` triggers it on PAL's layer for that player.
PAL is bundled in the mod's jar (jar-in-jar), so players install nothing extra.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .state import Store, StateError
from .validation import InputError

PAL_VERSION = "1.1.6+mc.1.21.1"
PAL_MAVEN = "https://repo.redlance.org/public"
PAL_BONES = ("body", "torso", "head", "right_arm", "left_arm", "right_leg", "left_leg", "right_item", "left_item", "cape", "elytra")
RIG = Path(__file__).resolve().parent / "resources" / "blockbench" / "player_rig"
PDIR = "models/player"
STEM = "player"


def rig_recipe() -> dict:
    """PAL's player bones with their documented pivots (Blockbench pixels, +X right, -Z forward) and the vanilla skin layout."""
    bones = [{"name": "body", "origin": [0, 12, 0]},
             {"name": "torso", "parent": "body", "origin": [0, 24, 0]},
             {"name": "head", "parent": "torso", "origin": [0, 24, 0]},
             {"name": "right_arm", "parent": "torso", "origin": [5, 22, 0]},
             {"name": "left_arm", "parent": "torso", "origin": [-5, 22, 0]},
             {"name": "right_item", "parent": "right_arm", "origin": [6, 12, -2]},
             {"name": "left_item", "parent": "left_arm", "origin": [-6, 12, -2]},
             {"name": "cape", "parent": "torso", "origin": [0, 24, 2]},
             {"name": "elytra", "parent": "torso", "origin": [0, 24, 2]},
             {"name": "right_leg", "parent": "body", "origin": [2, 12, 0]},
             {"name": "left_leg", "parent": "body", "origin": [-2, 12, 0]}]
    cubes = [{"name": "head", "bone": "head", "from": [-4, 24, -4], "to": [4, 32, 4], "uv_offset": [0, 0]},
             {"name": "torso", "bone": "torso", "from": [-4, 12, -2], "to": [4, 24, 2], "uv_offset": [16, 16]},
             {"name": "right_arm", "bone": "right_arm", "from": [4, 12, -2], "to": [8, 24, 2], "uv_offset": [40, 16]},
             {"name": "left_arm", "bone": "left_arm", "from": [-8, 12, -2], "to": [-4, 24, 2], "uv_offset": [32, 48]},
             {"name": "right_leg", "bone": "right_leg", "from": [0, 0, -2], "to": [4, 12, 2], "uv_offset": [0, 16]},
             {"name": "left_leg", "bone": "left_leg", "from": [-4, 0, -2], "to": [0, 12, 2], "uv_offset": [16, 48]}]
    return {"plan": STEM, "name": STEM, "identifier": STEM, "modid": "rigs", "model_type": "Entity", "texture_width": 64, "texture_height": 64,
            "visible_box": [2, 3, 1], "bones": bones, "cubes": cubes, "animations": [],
            "notes": "Player Animation Library bones and pivots. Animate these bones only; never rename, move or re-pivot them."}


def stage_rig(ws: Path) -> Path:
    """models/player/player.bbmodel from the committed rig, unless the designer already has one there."""
    target = ws / PDIR / f"{STEM}.bbmodel"
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RIG / "player.bbmodel", target)
    return target


def anim_key(item: str, action: str) -> str:
    return f"{item}_{action}"


# ------------------------------------------------------------------------------------------------ Java (generated support)

def support_java(package: str, mod_id: str) -> dict[str, str]:
    p = package
    payload = "\n".join([
        f"package {p}.playeranim;", "",
        f"import {p}.ModMain;",
        "import net.minecraft.network.RegistryFriendlyByteBuf;", "import net.minecraft.network.codec.ByteBufCodecs;", "import net.minecraft.network.codec.StreamCodec;",
        "import net.minecraft.network.protocol.common.custom.CustomPacketPayload;", "import net.minecraft.resources.ResourceLocation;", "",
        "/** Server -> clients: play (or stop) a player animation on the player with this entity id. */",
        "public record PlayerAnimPayload(int entityId, String animation, boolean stop) implements CustomPacketPayload {",
        '    public static final Type<PlayerAnimPayload> TYPE = new Type<>(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "player_anim"));',
        "    public static final StreamCodec<RegistryFriendlyByteBuf, PlayerAnimPayload> CODEC = StreamCodec.composite(",
        "        ByteBufCodecs.VAR_INT, PlayerAnimPayload::entityId, ByteBufCodecs.STRING_UTF8, PlayerAnimPayload::animation, ByteBufCodecs.BOOL, PlayerAnimPayload::stop,",
        "        PlayerAnimPayload::new);", "",
        "    @Override", "    public Type<? extends CustomPacketPayload> type() { return TYPE; }",
        "}", ""])
    anims = "\n".join([
        f"package {p}.playeranim;", "",
        "import net.fabricmc.api.ModInitializer;", "import net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry;",
        "import net.fabricmc.fabric.api.networking.v1.PlayerLookup;", "import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;",
        "import net.minecraft.server.level.ServerPlayer;", "import net.minecraft.world.entity.player.Player;", "",
        "/** Player animations (Player Animation Library): call play/stop on the server; the player and everyone who sees them get it. */",
        "public final class PlayerAnims implements ModInitializer {",
        "    @Override",
        "    public void onInitialize() { PayloadTypeRegistry.playS2C().register(PlayerAnimPayload.TYPE, PlayerAnimPayload.CODEC); }", "",
        "    /** animation = its key in assets/<mod>/player_animations/*.json (e.g. <item>_<action>). Does nothing on the client. */",
        "    public static void play(Player player, String animation) { send(player, new PlayerAnimPayload(player.getId(), animation, false)); }", "",
        "    public static void stop(Player player, String animation) { send(player, new PlayerAnimPayload(player.getId(), animation, true)); }", "",
        "    private static void send(Player player, PlayerAnimPayload payload) {",
        "        if (!(player instanceof ServerPlayer self)) return;",
        "        ServerPlayNetworking.send(self, payload);",
        "        for (ServerPlayer other : PlayerLookup.tracking(self)) if (other != self) ServerPlayNetworking.send(other, payload);",
        "    }",
        "}", ""])
    client = "\n".join([
        f"package {p}.client;", "",
        f"import {p}.ModMain;", f"import {p}.playeranim.PlayerAnimPayload;",
        "import com.zigythebird.playeranim.animation.PlayerAnimationController;", "import com.zigythebird.playeranim.api.PlayerAnimationAccess;",
        "import com.zigythebird.playeranim.api.PlayerAnimationFactory;", "import com.zigythebird.playeranimcore.enums.PlayState;",
        "import net.fabricmc.api.ClientModInitializer;", "import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;",
        "import net.minecraft.client.player.AbstractClientPlayer;", "import net.minecraft.resources.ResourceLocation;", "import net.minecraft.world.entity.Entity;", "",
        "/** PAL layer of this mod (priority 1600: above emotes, a gameplay action) and the payload that plays on it. */",
        "public final class PlayerAnimsClient implements ClientModInitializer {",
        '    public static final ResourceLocation LAYER = ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "actions");', "",
        "    @Override",
        "    public void onInitializeClient() {",
        "        PlayerAnimationFactory.ANIMATION_DATA_FACTORY.registerFactory(LAYER, 1600,",
        "            player -> new PlayerAnimationController(player, (controller, state, setter) -> PlayState.STOP));",
        "        ClientPlayNetworking.registerGlobalReceiver(PlayerAnimPayload.TYPE, (payload, context) -> {",
        "            if (context.client().level == null) return;",
        "            Entity entity = context.client().level.getEntity(payload.entityId());",
        "            if (!(entity instanceof AbstractClientPlayer player)) return;",
        "            if (!(PlayerAnimationAccess.getPlayerAnimationLayer(player, LAYER) instanceof PlayerAnimationController controller)) return;",
        "            if (payload.stop()) controller.stopTriggeredAnimation();",
        "            else if (!controller.triggerAnimation(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, payload.animation())))",
        '                ModMain.LOGGER.warn("Unknown player animation {}", payload.animation());',
        "        });",
        "    }",
        "}", ""])
    return {"playeranim/PlayerAnimPayload.java": payload, "playeranim/PlayerAnims.java": anims, "client/PlayerAnimsClient.java": client}


def patch_gradle(gradle: str, props: str) -> tuple[str, str] | None:
    """Add PAL (repository, jar-in-jar dependency, version). None when the build file has no single `dependencies {` block."""
    if "PlayerAnimationLibFabric" not in gradle:
        if gradle.count("\ndependencies {") != 1:
            return None
        repo = "    maven {\n        name = 'RedlanceMinecraft'\n        url = '%s'\n        content { includeGroup 'com.zigythebird.playeranim'; includeGroup 'com.zigythebird' }\n    }" % PAL_MAVEN
        dep = '    modImplementation include("com.zigythebird.playeranim:PlayerAnimationLibFabric:${project.pal_version}")'
        gradle = gradle.replace("\ndependencies {", "\nrepositories {\n" + repo + "\n}\n\ndependencies {\n" + dep, 1)
    if "pal_version" not in props:
        props = props.rstrip("\n") + f"\npal_version={PAL_VERSION}\n"
    return gradle, props


def patch_fabric_mod(text: str, package: str) -> str | None:
    try:
        d = json.loads(text)
    except ValueError:
        return None
    eps = d.setdefault("entrypoints", {})
    for key, entry in (("main", f"{package}.playeranim.PlayerAnims"), ("client", f"{package}.client.PlayerAnimsClient")):
        lst = eps.setdefault(key, [])
        if not isinstance(lst, list):
            return None
        if entry not in lst:
            lst.append(entry)
    d.setdefault("depends", {}).setdefault("player_animation_library", "*")
    return json.dumps(d, indent=2) + "\n"


def ensure_support(ws: Path, spec) -> tuple[list[str], list[str]]:
    """PAL in the build, the entrypoints and the support classes: patched when the manifest vouches, otherwise for the coder."""
    from .model3d import _known
    jdir = f"src/main/java/{spec.package.replace('.', '/')}"
    written, coder = [], []
    for name, src in support_java(spec.package, spec.mod_id).items():
        rel = f"{jdir}/{name}"; f = ws / rel
        if not f.is_file():
            f.parent.mkdir(parents=True, exist_ok=True); f.write_text(src, encoding="utf8"); written.append(rel)
        elif f.read_text(encoding="utf8") != src:
            if _known(ws, rel):
                f.write_text(src, encoding="utf8"); written.append(rel)
            else:
                coder.append(f"{rel} has edits the controller did not record; make it match its current version, keeping what the edits need:\n{src}")
    gradle, props = ws / "build.gradle", ws / "gradle.properties"
    if "PlayerAnimationLibFabric" not in gradle.read_text(encoding="utf8") or "pal_version" not in props.read_text(encoding="utf8"):
        patched = patch_gradle(gradle.read_text(encoding="utf8"), props.read_text(encoding="utf8")) if _known(ws, "build.gradle") and _known(ws, "gradle.properties") else None
        if patched is None:
            coder.append(f"add Player Animation Library to the build: maven {PAL_MAVEN} (group com.zigythebird.playeranim), "
                         f'modImplementation include("com.zigythebird.playeranim:PlayerAnimationLibFabric:${{project.pal_version}}"), pal_version={PAL_VERSION} in gradle.properties')
        else:
            gradle.write_text(patched[0], encoding="utf8"); props.write_text(patched[1], encoding="utf8"); written += ["build.gradle", "gradle.properties"]
    fmj_rel = "src/main/resources/fabric.mod.json"; fmj = ws / fmj_rel
    text = fmj.read_text(encoding="utf8")
    if f"{spec.package}.playeranim.PlayerAnims" not in text or f"{spec.package}.client.PlayerAnimsClient" not in text:
        patched = patch_fabric_mod(text, spec.package) if _known(ws, fmj_rel) else None
        if patched is None:
            coder.append(f"in {fmj_rel}: add \"{spec.package}.playeranim.PlayerAnims\" to the main entrypoints, \"{spec.package}.client.PlayerAnimsClient\" "
                         "to the client entrypoints, and depend on player_animation_library")
        else:
            fmj.write_text(patched, encoding="utf8"); written.append(fmj_rel)
    return written, coder


# ------------------------------------------------------------------------------------------------ validate + install

def validate(ws: Path, wanted: list[str]) -> dict:
    """models/player/player.animation.json: every wanted clip present with keyframes, only PAL bones, no other clip changed shape."""
    f = ws / PDIR / f"{STEM}.animation.json"
    try:
        anims = json.loads(f.read_text(encoding="utf8")).get("animations") or {}
    except (OSError, ValueError):
        raise InputError(f"{PDIR}/{STEM}.animation.json is missing or not JSON (export the player rig's animations)") from None
    problems = []
    for key in wanted:
        clip = anims.get(key)
        if not clip or not clip.get("bones"):
            problems.append(f"player animation {key!r} is missing or has no keyframes (name the clip exactly {key})")
    for key, clip in anims.items():
        stray = sorted(set((clip or {}).get("bones") or {}) - set(PAL_BONES))
        if stray:
            problems.append(f"player animation {key!r} moves bones the player does not have: {stray} (only {', '.join(PAL_BONES)})")
        if not re.fullmatch(r"[a-z0-9_./-]{1,64}", key):
            problems.append(f"player animation key {key!r}: lowercase letters, digits and _ only (it becomes <mod>:{key})")
    if problems:
        raise InputError("; ".join(problems[:8]))
    return {"clips": sorted(anims)}


def install(store: Store, pid: str, wanted: list[str], *, run_id: str, actor: str) -> dict:
    from .fabric import accept_changes
    from .spec import read_spec
    proj = store.project(pid); ws = Path(proj["root"]); spec = read_spec(proj["spec"])
    info = validate(ws, wanted)
    rel = f"src/main/resources/assets/{pid}/player_animations/{STEM}.json"
    (ws / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ws / PDIR / f"{STEM}.animation.json", ws / rel)
    written, coder = ensure_support(ws, spec)
    accept_changes(ws, run_id=run_id + ":player", actor=actor, changed=sorted(set(written + [rel])))
    store.add_event(pid, "controller", "PLAYER_ANIMS_INSTALLED", {"run": run_id, "clips": info["clips"], "coder": bool(coder)})
    return {"installed": [rel] + written, "clips": info["clips"], "coder": coder}
