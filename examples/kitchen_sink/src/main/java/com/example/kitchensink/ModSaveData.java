package com.example.kitchensink;

import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.level.saveddata.SavedData;

/** Compiled reference for the `data` skill: per-world persistent data. */
public class ModSaveData extends SavedData {
    public static final SavedData.Factory<ModSaveData> FACTORY = new SavedData.Factory<>(ModSaveData::new, ModSaveData::load, null);
    public int bossesSlain;

    public static ModSaveData get(MinecraftServer server) {
        return server.overworld().getDataStorage().computeIfAbsent(FACTORY, ModMain.MOD_ID + "_data");
    }

    public static ModSaveData load(CompoundTag tag, HolderLookup.Provider registries) {
        ModSaveData d = new ModSaveData();
        d.bossesSlain = tag.getInt("bossesSlain");
        return d;
    }

    @Override
    public CompoundTag save(CompoundTag tag, HolderLookup.Provider registries) {
        tag.putInt("bossesSlain", bossesSlain);
        return tag;
    }
}
