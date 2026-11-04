package com.example.kitchensink;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonSyntaxException;
import net.fabricmc.loader.api.FabricLoader;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** Compiled reference for the `polish` skill (simple JSON config). */
public final class ModConfig {
    public int manaMax = 100;
    public boolean showHud = true;
    private static final Path FILE = FabricLoader.getInstance().getConfigDir().resolve(ModMain.MOD_ID + ".json");

    public static ModConfig load() {
        Gson gson = new GsonBuilder().setPrettyPrinting().create();
        try {
            if (Files.exists(FILE)) {
                ModConfig c = gson.fromJson(Files.readString(FILE), ModConfig.class);
                if (c != null) return c;
            }
        } catch (IOException | JsonSyntaxException e) {
            ModMain.LOGGER.warn("Bad config, using defaults", e);
        }
        ModConfig c = new ModConfig();
        c.save();
        return c;
    }

    public void save() {
        try {
            Files.writeString(FILE, new GsonBuilder().setPrettyPrinting().create().toJson(this));
        } catch (IOException e) {
            ModMain.LOGGER.warn("Could not save config", e);
        }
    }
}
