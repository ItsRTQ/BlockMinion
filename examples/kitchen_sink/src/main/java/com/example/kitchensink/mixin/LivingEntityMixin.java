package com.example.kitchensink.mixin;

import com.example.kitchensink.EffectsExample;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.damagesource.DamageTypes;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Compiled reference for the `mixins` skill: a TAIL inject and a cancellable HEAD inject. */
@Mixin(LivingEntity.class)
public abstract class LivingEntityMixin {
    @Inject(method = "jumpFromGround", at = @At("TAIL"))
    private void kitchen_sink$boostJump(CallbackInfo ci) {
        LivingEntity self = (LivingEntity) (Object) this;
        if (self instanceof Player p && p.getItemBySlot(EquipmentSlot.FEET).is(com.example.kitchensink.ModMain.CRYSTAL_BOOTS)) {
            self.setDeltaMovement(self.getDeltaMovement().add(0, 0.2, 0));
        }
    }

    @Inject(method = "hurt", at = @At("HEAD"), cancellable = true)
    private void kitchen_sink$cactusImmunity(DamageSource source, float amount, CallbackInfoReturnable<Boolean> cir) {
        LivingEntity self = (LivingEntity) (Object) this;
        if (source.is(DamageTypes.CACTUS) && self.hasEffect(EffectsExample.CRYSTAL_SIGHT)) cir.setReturnValue(false);
    }
}
