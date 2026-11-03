---
name: mixins
description: When and how to write a Mixin on Fabric 1.21.1 (Mojang mappings) — the last resort when no Fabric API hook exists. Strict rules — most requests that sound like "I need a mixin" have an API event instead.
---

# Mixins — last resort, with rules

A Mixin rewrites vanilla bytecode at load time. It breaks on every Minecraft update, conflicts with other mods touching the
same method, and is invisible to the controller's checks. **Before writing one, prove no API hook exists**: the `events`,
`data`, `client-ui`, `loot-and-trades`, `effects`, `items` skills cover 90% of mechanics. If the user asked for a mixin by
name, still look for the hook first and say so in `risks`.

Legitimate cases: changing vanilla behaviour with no hook (jump height for every player, a vanilla block's hardness at runtime,
hiding the vanilla hunger bar), reading a private field, injecting into a vanilla screen.

## Setup (already in generated projects)
`fabric.mod.json` has `"mixins": ["<mod>.mixins.json"]` only if the file exists — create `src/main/resources/<mod>.mixins.json`:
```json
{"required": true, "package": "<package>.mixin", "compatibilityLevel": "JAVA_21", "mixins": ["ServerPlayerMixin"], "client": ["GuiMixin"], "injectors": {"defaultRequire": 1}}
```
and add `"mixins": ["<mod>.mixins.json"]` to `fabric.mod.json`. Compiled reference: `examples/kitchen_sink/.../mixin/LivingEntityMixin.java`.

## Patterns (Mojang names; verify the target signature in the decompiled sources under build/ or with the IDE)
```java
@Mixin(LivingEntity.class)
public abstract class LivingEntityMixin {
    // add behaviour after a method, without changing its result
    @Inject(method = "jumpFromGround", at = @At("TAIL"))
    private void kitchen_sink$boostJump(CallbackInfo ci) {
        LivingEntity self = (LivingEntity) (Object) this;
        if (self instanceof Player p && p.getItemBySlot(EquipmentSlot.FEET).is(ModMain.CRYSTAL_BOOTS)) self.setDeltaMovement(self.getDeltaMovement().add(0, 0.2, 0));
    }
    // read a private field / call a private method
    @Shadow protected abstract float getJumpPower();
    // cancel a method under a condition (HEAD + cancellable)
    @Inject(method = "hurt", at = @At("HEAD"), cancellable = true)
    private void kitchen_sink$immune(DamageSource source, float amount, CallbackInfoReturnable<Boolean> cir) {
        if (source.is(DamageTypes.CACTUS) && ((LivingEntity) (Object) this).hasEffect(EffectsExample.CRYSTAL_SIGHT)) cir.setReturnValue(false);
    }
}
```
- `@At("HEAD")` runs first, `"TAIL"` last, `"RETURN"` before every return; `cancellable = true` only when you call `ci.cancel()`/`setReturnValue`.
- Name injected methods `<mod>$name` to avoid clashes. Target names are Mojang mappings (Loom remaps at build).
- Client-only mixins (screens, HUD) go under `"client"` in the mixins json and in the `client` package.
- Prefer `@Inject` over `@Overwrite` (overwrite = guaranteed conflicts). `@Redirect`/`@ModifyVariable` only with a comment explaining why.
- Accessors for private fields: an `@Mixin(Target.class) interface TargetAccessor { @Accessor("fieldName") int getField(); }`.

## Report
In the handoff `risks`: the target class/method, why no API hook was possible, and that it needs re-verification on every Minecraft update.
