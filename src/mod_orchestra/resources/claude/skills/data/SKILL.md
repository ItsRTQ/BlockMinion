---
name: data
description: Persistent data on Fabric 1.21.1 (Mojang mappings) — per-player values (mana, levels, cooldowns) with the Data Attachment API, per-world data with SavedData, and per-item data with a custom DataComponentType. Use for any "system" that remembers something.
---

# Persistent data (1.21.1, Mojmap). Compiled reference: `examples/kitchen_sink/.../DataExample.java`, `ModSaveData.java`

Three places to keep state — pick by what the value belongs to:

| Belongs to | API | Survives |
|---|---|---|
| a player (mana, level, cooldown) | **Data Attachment** `AttachmentType<T>` | logout, restart; optionally death |
| the world / server (global counters, bosses killed) | **SavedData** | restart (saved in the world folder) |
| an item stack (charges, owner, mode) | **DataComponentType<T>** | the stack itself (also synced to the client and shown in NBT-aware tooltips) |

## Player attachment
```java
public static final AttachmentType<Integer> MANA = AttachmentRegistry.<Integer>builder()
    .persistent(Codec.INT)                       // saved with the player
    .copyOnDeath()                               // keep across death (omit to reset)
    .initializer(() -> 0)
    .buildAndRegister(ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "mana"));

int mana = player.getAttachedOrCreate(MANA);     // read (creates the initial value)
player.setAttached(MANA, Math.min(100, mana + 1)); // write
```
`net.fabricmc.fabric.api.attachment.v1.AttachmentRegistry` / `AttachmentType`, `com.mojang.serialization.Codec`. Works on any `Entity`, `BlockEntity`, `ServerLevel`, chunk.
Change on the **server** (`ServerPlayer`); the client does not see attachments unless you send them (see client-ui: server→client payload).

## World SavedData
```java
public class ModSaveData extends SavedData {
    public static final SavedData.Factory<ModSaveData> FACTORY = new SavedData.Factory<>(ModSaveData::new, ModSaveData::load, null);
    public int bossesSlain;
    public static ModSaveData get(MinecraftServer server) { return server.overworld().getDataStorage().computeIfAbsent(FACTORY, ModMain.MOD_ID + "_data"); }
    public static ModSaveData load(CompoundTag tag, HolderLookup.Provider registries) { ModSaveData d = new ModSaveData(); d.bossesSlain = tag.getInt("bossesSlain"); return d; }
    @Override public CompoundTag save(CompoundTag tag, HolderLookup.Provider registries) { tag.putInt("bossesSlain", bossesSlain); return tag; }
}
// use: ModSaveData d = ModSaveData.get(server); d.bossesSlain++; d.setDirty();   // setDirty() or it is never written
```
`net.minecraft.world.level.saveddata.SavedData`, `net.minecraft.nbt.CompoundTag`, `net.minecraft.core.HolderLookup`.

## Item data component
```java
public static final DataComponentType<Integer> CHARGE = Registry.register(BuiltInRegistries.DATA_COMPONENT_TYPE, ResourceLocation.fromNamespaceAndPath(ModMain.MOD_ID, "charge"),
    DataComponentType.<Integer>builder().persistent(Codec.INT).networkSynchronized(ByteBufCodecs.VAR_INT).build());
int c = stack.getOrDefault(CHARGE, 0);  stack.set(CHARGE, c + 1);  stack.remove(CHARGE);
// default on a new item: new Item.Properties().component(CHARGE, 3)
```
`net.minecraft.core.component.DataComponentType`, `net.minecraft.network.codec.ByteBufCodecs`. Records as components: `RecordCodecBuilder` codec + `StreamCodec.composite`.
Never store state in static maps keyed by player name — it is lost on restart and breaks on multiplayer.
