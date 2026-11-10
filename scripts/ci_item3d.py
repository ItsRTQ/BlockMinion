"""CI: give the generated ci_mod a scaled mob and a 3D sword the way the controller would, so Gradle compiles the code
those features add (Attributes.SCALE in an entity, the 3D item renderer classes, the client entrypoint)."""
import json
import sys
from pathlib import Path

from mod_orchestra.model3d import install_item3d, request_item3d
from mod_orchestra.models import set_mob_scale
from mod_orchestra.skin import encode_png
from mod_orchestra.state import Store

store = Store(None)
pid, item = "ci_mod", "ci_sword"
print("scale:", set_mob_scale(store, pid, "ci_stalker", 1.5)["how"])
task = request_item3d(store, pid, item, "CI")["task"]
ws = Path(store.project(pid)["root"]); d = ws / "models/items3d"; d.mkdir(parents=True, exist_ok=True)
px = bytes(c for y in range(16) for x in range(16) for c in ((90, 90, 110, 255) if (x + y) % 3 else (200, 200, 220, 255)))
png = encode_png(16, 16, px)
geo = {"format_version": "1.12.0", "minecraft:geometry": [{"description": {"identifier": f"geometry.{item}", "texture_width": 16, "texture_height": 16},
       "bones": [{"name": "blade", "pivot": [0, 0, 0], "cubes": [{"origin": [-1, 2, -0.5], "size": [2, 13, 1], "uv": [0, 0]}]},
                 {"name": "guard", "parent": "blade", "pivot": [0, 2, 0], "cubes": [{"origin": [-3, 2, -1], "size": [6, 1, 2], "uv": [0, 14]}]}]}]}
anim = {"format_version": "1.8.0", "animations": {f"animation.{item}.idle": {"loop": True, "animation_length": 2,
        "bones": {"blade": {"rotation": {"0.0": {"vector": [0, 0, 0]}, "1.0": {"vector": [0, 10, 0]}, "2.0": {"vector": [0, 0, 0]}}}}}}}
(d / f"{item}.geo.json").write_text(json.dumps(geo)); (d / f"{item}.animation.json").write_text(json.dumps(anim))
(d / f"{item}.png").write_bytes(png); (d / f"{item}_render.png").write_bytes(png); (d / f"{item}.bbmodel").write_text("{}")
out = install_item3d(store, pid, task, item, run_id="ci-item3d", actor="ci")
print("item3d installed:", out["installed"], "animated:", out["animated"], "coder:", out["wire_task"])
# A 3D block wired the way the controller does it (ModMain line, entrypoints, Block3D* classes)
from mod_orchestra.blocks3d import install_block3d, request_block3d
btask = request_block3d(store, pid, "ci_ore", "CI")["task"]
bd = ws / "models/blocks3d"; bd.mkdir(parents=True, exist_ok=True)
bgeo = {"format_version": "1.12.0", "minecraft:geometry": [{"description": {"identifier": "geometry.ci_ore", "texture_width": 16, "texture_height": 16},
        "bones": [{"name": "rock", "pivot": [0, 0, 0], "cubes": [{"origin": [-6, 0, -6], "size": [12, 10, 12], "uv": [0, 0]}]}]}]}
banim = {"format_version": "1.8.0", "animations": {"animation.ci_ore.idle": {"loop": True, "animation_length": 2, "bones": {"rock": {"position": {"0.0": {"vector": [0, 0, 0]}, "1.0": {"vector": [0, 1, 0]}}}}},
         "animation.ci_ore.crack": {"animation_length": 0.5, "bones": {"rock": {"scale": {"0.0": {"vector": [1, 1, 1]}, "0.25": {"vector": [1.1, 0.9, 1.1]}}}}}}}
(bd / "ci_ore.geo.json").write_text(json.dumps(bgeo)); (bd / "ci_ore.animation.json").write_text(json.dumps(banim))
(bd / "ci_ore.png").write_bytes(png); (bd / "ci_ore_render.png").write_bytes(png); (bd / "ci_ore.bbmodel").write_text("{}")
bout = install_block3d(store, pid, btask, "ci_ore", run_id="ci-block3d", actor="ci")
print("block3d installed:", bout["installed"], "wire:", bout["wire_task"], "anim:", bout["anim_task"])
if bout["wire_task"]:
    sys.exit("the controller could not wire a 3D block in a freshly generated project by itself")

# The coder's recipe for actions, filled in as a coder would (not registered): Gradle proves the helpers and the recipe compile.
java = ws / "src/main/java/com/example/cimod/gear/CiActionItem.java"; java.parent.mkdir(parents=True, exist_ok=True)
java.write_text("""package com.example.cimod.gear;

import com.example.cimod.ModMain;
import com.example.cimod.client.Item3DGeoRenderer;
import com.example.cimod.model3d.Item3DActions;
import net.minecraft.client.renderer.BlockEntityWithoutLevelRenderer;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResultHolder;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import software.bernie.geckolib.animatable.GeoItem;
import software.bernie.geckolib.animatable.client.GeoRenderProvider;
import software.bernie.geckolib.animatable.instance.AnimatableInstanceCache;
import software.bernie.geckolib.animation.AnimatableManager;
import software.bernie.geckolib.util.GeckoLibUtil;
import java.util.function.Consumer;

public class CiActionItem extends Item implements GeoItem {
    private final AnimatableInstanceCache cache = GeckoLibUtil.createInstanceCache(this);

    public CiActionItem(Properties properties) { super(properties); Item3DActions.init(this); }

    @Override
    public void registerControllers(AnimatableManager.ControllerRegistrar controllers) {
        Item3DActions.controllers(this, controllers, "ci_sword", true, "use", "attack");
    }

    @Override
    public AnimatableInstanceCache getAnimatableInstanceCache() { return cache; }

    @Override
    public void createGeoRenderer(Consumer<GeoRenderProvider> consumer) {
        consumer.accept(new GeoRenderProvider() {
            private Item3DGeoRenderer<CiActionItem> renderer;
            @Override
            public BlockEntityWithoutLevelRenderer getGeoItemRenderer() {
                if (renderer == null) renderer = new Item3DGeoRenderer<>(ModMain.MOD_ID, "ci_sword");
                return renderer;
            }
        });
    }

    @Override
    public InteractionResultHolder<ItemStack> use(Level level, Player player, InteractionHand hand) {
        ItemStack stack = player.getItemInHand(hand);
        Item3DActions.trigger(this, player, stack, "use");
        com.example.cimod.playeranim.PlayerAnims.play(player, "ci_sword_use");   // the player's body, through Player Animation Library
        com.example.cimod.model3d.Block3DEntity.trigger(level, player.blockPosition().below(), "crack");   // a 3D block's action
        return InteractionResultHolder.success(stack);
    }

    @Override
    public void releaseUsing(ItemStack stack, Level level, LivingEntity entity, int timeLeft) {
        Item3DActions.stop(this, entity, stack, "use");   // a looping action ends
    }

    @Override
    public boolean hurtEnemy(ItemStack stack, LivingEntity target, LivingEntity attacker) {
        Item3DActions.trigger(this, attacker, stack, "attack");
        return super.hurtEnemy(stack, target, attacker);
    }
}
""")
from mod_orchestra.fabric import accept_changes
from mod_orchestra import playeranim
from mod_orchestra.spec import read_spec
pa_written, pa_coder = playeranim.ensure_support(ws, read_spec(store.project(pid)["spec"]))   # PAL in the build + its classes, compiled below
print("player animation support:", pa_written, "coder:", pa_coder)
if pa_coder:
    sys.exit("the controller could not add Player Animation Library to a freshly generated project by itself")
accept_changes(ws, run_id="ci-playeranim", actor="ci", changed=pa_written)
accept_changes(ws, run_id="ci-recipe", actor="ci", changed=[str(java.relative_to(ws)).replace("\\", "/")])
print("recipe class written:", java.relative_to(ws))
if out["wire_task"]:
    sys.exit("the controller could not wire a freshly generated project by itself")
