package com.example.kitchensink;

import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.projectile.ThrowableItemProjectile;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.phys.HitResult;

/** Compiled reference for the `items` skill: a thrown projectile that deals damage. */
public class CrystalBoltEntity extends ThrowableItemProjectile {
    public CrystalBoltEntity(EntityType<? extends CrystalBoltEntity> type, Level level) {
        super(type, level);
    }

    public CrystalBoltEntity(Level level, LivingEntity shooter) {
        super(ModMain.CRYSTAL_BOLT, shooter, level);
    }

    @Override
    protected Item getDefaultItem() {
        return ModMain.SKY_CRYSTAL;
    }

    @Override
    protected void onHitEntity(EntityHitResult hit) {
        super.onHitEntity(hit);
        hit.getEntity().hurt(damageSources().thrown(this, getOwner()), 4.0F);
    }

    @Override
    protected void onHit(HitResult result) {
        super.onHit(result);
        if (!level().isClientSide) {
            level().broadcastEntityEvent(this, (byte) 3);
            discard();
        }
    }
}
