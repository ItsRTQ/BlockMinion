---
name: polish
description: Small finishing touches on Fabric 1.21.1 (Mojang mappings) — particles, animated textures (.mcmeta), custom advancements, a simple JSON config file. Use when a feature needs feedback effects or settings.
---

# Polish: particles, animated textures, advancements, config

## Particles (vanilla types, no registration needed)
Server side (visible to everyone): `((ServerLevel) level).sendParticles(ParticleTypes.HAPPY_VILLAGER, x, y, z, 10, 0.5, 0.5, 0.5, 0.02);`
Client side (only this client): `level.addParticle(ParticleTypes.CRIT, x, y, z, dx, dy, dz);`
Common types: `HAPPY_VILLAGER`, `CRIT`, `ENCHANT`, `FLAME`, `SMOKE`, `END_ROD`, `SOUL_FIRE_FLAME`, `WITCH`. `net.minecraft.core.particles.ParticleTypes`.
Custom particle textures are a larger feature (ParticleType registration + client factory + JSON) — only when asked.

## Animated texture
Put frames stacked vertically in one PNG (16×64 = 4 frames) and add `assets/<mod>/textures/item/<id>.png.mcmeta`:
```json
{"animation": {"frametime": 4}}
```
`frametime` in ticks; `"interpolate": true` blends frames; `"frames": [0,1,2,1]` custom order.

## Custom advancement (datapack JSON, `data/<mod>/advancement/<name>.json`)
```json
{"parent": "minecraft:story/root",
 "display": {"icon": {"id": "<mod>:sky_crystal"}, "title": {"translate": "advancement.<mod>.first_crystal.title"}, "description": {"translate": "advancement.<mod>.first_crystal.desc"}, "frame": "task"},
 "criteria": {"got_it": {"trigger": "minecraft:inventory_changed", "conditions": {"items": [{"items": ["<mod>:sky_crystal"]}]}}}}
```
Frames: `task`, `goal`, `challenge`. Lang keys for title/desc. A root advancement (no parent) needs `"background": "minecraft:textures/block/stone.png"` in display.

## Simple config (JSON in the config folder, Gson is on the classpath)
```java
public final class ModConfig {
    public int manaMax = 100; public boolean showHud = true;
    private static final Path FILE = FabricLoader.getInstance().getConfigDir().resolve(ModMain.MOD_ID + ".json");
    public static ModConfig load() {
        Gson gson = new GsonBuilder().setPrettyPrinting().create();
        try { if (Files.exists(FILE)) return gson.fromJson(Files.readString(FILE), ModConfig.class); } catch (IOException | JsonSyntaxException e) { ModMain.LOGGER.warn("Bad config, using defaults", e); }
        ModConfig c = new ModConfig(); c.save(); return c;
    }
    public void save() { try { Files.writeString(FILE, new GsonBuilder().setPrettyPrinting().create().toJson(this)); } catch (IOException e) { ModMain.LOGGER.warn("Could not save config", e); } }
}
```
`net.fabricmc.loader.api.FabricLoader`, `com.google.gson.*`. Load once in `onInitialize`; keep it in a static field. Compiled reference: `examples/kitchen_sink/.../ModConfig.java`.
