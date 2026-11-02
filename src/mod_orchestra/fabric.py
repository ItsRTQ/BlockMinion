"""Small deterministic Fabric 1.21.1 prototype generator (Mojang mappings, Loom 1.18).

No generated executable is run and no downloaded script is evaluated.
The output is SOURCE ONLY until a separate verified Gradle build occurs.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import secrets
import shutil
import struct
import time
import zlib
from pathlib import Path
from .state import StateError
from .config import PROFILE, WRAPPER_DIR, WRAPPER_FILES, GENERATOR_VERSION
from .spec import Spec, Recipe, Drop, resolve_ingredient, resolve_result
from .textures import tinted_item_png, armor_layer_png, material_colors
from .gear import gear_registrations, gear_item_ids, gear_recipes, tier_java, cls as gear_cls
from .geckolib import (GECKOLIB_VERSION, gradle_dependency_lines, main_registrations, entity_java, renderer_java,
                       client_init_java, placeholder_geo, placeholder_animation, entity_loot, class_name)
from .validation import InputError, safe_inside, ensure_new_directory


def placeholder_png(name: str, size: int = 16, height: int | None = None) -> bytes:
    """Deterministic pixel art placeholder PNG using only Python stdlib (size x height, default square)."""
    width, height = size, height or size
    digest = hashlib.sha256(name.encode()).digest()
    main = (40 + digest[0] % 170, 40 + digest[1] % 170, 40 + digest[2] % 170)
    outline = tuple(max(0, c - 50) for c in main)
    shine = tuple(min(255, c + 50) for c in main)
    rows = []
    for y in range(height):
        pixels = []
        for x in range(width):
            edge = x in (0, width - 1) or y in (0, height - 1)
            alternate = ((x // 4) + (y // 4)) % 2 == 0
            color = outline if edge else shine if alternate else main
            pixels.extend([*color, 255])
        rows.append(b"\x00" + bytes(pixels))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")


STAGING_DIRNAME = ".staging"
STAGING_ORPHAN_AGE = 3600  # seconds; stagings older than this are leftovers of a dead process


def staging_dir_for(spec: Spec, directory: Path) -> Path:
    """projects/.staging/<name-slug>-<id>-<UTC timestamp>-<4 hex>: readable, unique per attempt (slug omitted when it equals the id)."""
    slug = re.sub(r"[^a-z0-9]+", "_", spec.name.lower()).strip("_")[:40]
    label = spec.mod_id if slug in ("", spec.mod_id) else f"{slug}-{spec.mod_id}"
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + secrets.token_hex(2)  # unique within a second
    return directory.parent / STAGING_DIRNAME / f"{label}-{stamp}"


def sweep_orphan_stagings(projects_root: Path, max_age: int = STAGING_ORPHAN_AGE) -> list[str]:
    """Remove stagings older than max_age (a crashed generate never got to rename). Returns what was removed."""
    staging_root = projects_root / STAGING_DIRNAME
    removed: list[str] = []
    if not staging_root.is_dir():
        return removed
    now = time.time()
    for entry in staging_root.iterdir():
        if entry.is_dir() and not entry.is_symlink() and now - entry.stat().st_mtime > max_age:
            shutil.rmtree(entry, ignore_errors=True)
            removed.append(entry.name)
    return removed


def generate(spec: Spec, directory: Path) -> dict:
    """Write an entirely new workspace with a generated/UNVERIFIED status.

    SEC-001 atomic staging: files are written and hash-validated in a sibling staging
    directory, then moved into place with one os.replace(). The final path either does
    not exist or is a complete, validated workspace; a crash mid-way leaves only a
    staging directory that the next generate sweeps.
    """
    directory = Path(directory).expanduser()
    controller_dir = None
    if directory.exists():
        # The controller may already own <workspace>/.mod-orchestra (run logs from an interpreter pass made before
        # generation). That is not user content: keep it and treat the directory as empty otherwise.
        entries = [e for e in directory.iterdir()] if not directory.is_symlink() else [None]
        if entries == [directory / ".mod-orchestra"] and not (directory / ".mod-orchestra").is_symlink():
            controller_dir = directory / ".mod-orchestra"
        else:
            ensure_new_directory(directory)  # raises on nonempty/symlink; empty dir is replaced below
    sweep_orphan_stagings(directory.parent)
    staging = staging_dir_for(spec, directory)
    staging.parent.mkdir(parents=True, exist_ok=True)
    try:
        output = _generate_into(spec, staging)
        checked = validate_generated(staging)
        if checked["status"] != "PASS":
            raise StateError("Staged source failed integrity validation before install: " + str(checked["problems"][:5]))
        if controller_dir is not None:
            # merge the controller's pre-generation files (runs/) into the staged .mod-orchestra, then clear the dir
            for item in controller_dir.iterdir():
                target = staging / ".mod-orchestra" / item.name
                if target.exists():
                    for sub in item.iterdir():
                        shutil.move(str(sub), str(target / sub.name))
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    shutil.move(str(item), str(target))
            shutil.rmtree(controller_dir)
        if directory.exists():
            directory.rmdir()  # known empty now
        os.replace(staging, directory)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    output["path"] = str(directory)
    output["manifest"] = str(directory / ".mod-orchestra" / "generation-manifest.json")
    output["staged_as"] = staging.name
    output["static_validation"] = checked | {"root": str(directory)}
    return output


def _generate_into(spec: Spec, directory: Path) -> dict:
    if spec.questions:
        raise InputError("Cannot generate until blocking questions are resolved: " + "; ".join(spec.questions))
    if not spec.features:
        raise InputError("At least one deterministic item/block feature required")
    if spec.profile != PROFILE["id"]:
        raise InputError("Unsupported target profile")
    directory = Path(directory).expanduser()
    ensure_new_directory(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    def put(relative: str, content: str | bytes) -> None:
        target = safe_inside(directory, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise InputError("No overwrite permitted: " + relative)
        raw = content.encode("utf-8") if isinstance(content, str) else content
        with target.open("xb") as f:
            f.write(raw)
        written[relative] = hashlib.sha256(raw).hexdigest()

    p = PROFILE
    put("settings.gradle", f"""pluginManagement {{
    repositories {{
        maven {{
            name = 'Fabric'
            url = 'https://maven.fabricmc.net/'
        }}
        mavenCentral()
        gradlePluginPortal()
    }}
}}

rootProject.name = '{spec.mod_id}'
""")
    put("gradle.properties", f"""org.gradle.jvmargs=-Xmx2G
org.gradle.parallel=true
org.gradle.configuration-cache=true

# Fabric Properties (profile {p['id']}; see https://fabricmc.net/develop)
minecraft_version={p['minecraft']}
loader_version={p['fabric_loader']}
loom_version={p['loom']}

# Mod Properties
version=1.0.0
group={spec.package}
archives_base_name={spec.mod_id}

# Dependencies
fabric_api_version={p['fabric_api']}
{"geckolib_version=" + GECKOLIB_VERSION if spec.mobs else ""}
""")
    gecko_repo, gecko_dep = "", ""
    if spec.mobs:
        repo_block, dep_line = gradle_dependency_lines()
        gecko_repo = "repositories {\n" + repo_block + "\n}\n\n"
        gecko_dep = dep_line + "\n"
    put("build.gradle", f"""plugins {{
    id '{p['loom_plugin']}' version "${{loom_version}}"
}}

base {{ archivesName = project.archives_base_name }}

loom {{
    mods {{
        "{spec.mod_id}" {{
            sourceSet sourceSets.main
        }}
    }}
}}

{gecko_repo}dependencies {{
    // To change the versions see the gradle.properties file
    minecraft "com.mojang:minecraft:${{project.minecraft_version}}"
    mappings loom.officialMojangMappings()
    modImplementation "net.fabricmc:fabric-loader:${{project.loader_version}}"
    modImplementation "net.fabricmc.fabric-api:fabric-api:${{project.fabric_api_version}}"
{gecko_dep}}}

processResources {{
    def version = project.version
    inputs.property "version", version
    filesMatching("fabric.mod.json") {{
        expand "version": version
    }}
}}

tasks.withType(JavaCompile).configureEach {{
    it.options.release = {p['java_major']}
    it.options.encoding = 'UTF-8'
}}

java {{
    sourceCompatibility = JavaVersion.VERSION_{p['java_major']}
    targetCompatibility = JavaVersion.VERSION_{p['java_major']}
}}
""")
    # Official Gradle wrapper (Apache-2.0), hash-verified against resources/gradle-wrapper/PROVENANCE.md.
    for relative, expected in WRAPPER_FILES.items():
        put(relative, verified_wrapper_file(relative, expected))
    if os.name != "nt":
        gradlew = directory / "gradlew"
        gradlew.chmod(gradlew.stat().st_mode | 0o111)
    put("gradle/wrapper/gradle-wrapper.properties", f"""distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-{p['gradle']}-bin.zip
distributionSha256Sum={p['gradle_dist_sha256']}
networkTimeout=10000
retries=0
retryBackOffMs=500
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""")
    put(".gitignore", ".gradle/\nbuild/\nrun/\n.idea/\n*.class\n")
    put("README.md", f"""# {spec.name}

Generated by Minecraft Mod Orchestra. **SOURCE GENERATED — NOT BUILD VERIFIED.**

Minecraft {p['minecraft']} / Fabric Loader {p['fabric_loader']} / Loom {p['loom']} / Mojang mappings / compile target Java {p['java_major']}.

### Build

1. Review generated source and dependencies.
2. Install JDK {p['gradle_jdk_major']} (required to run Gradle {p['gradle']} + Loom). Sources compile with `--release {p['java_major']}`, so no separate JDK {p['java_major']} is needed.
3. Run `./gradlew build` on Linux/macOS or `gradlew.bat build` on Windows. The wrapper is the official Gradle {p['gradle']} wrapper (hash-verified, Apache-2.0) and checks the distribution download against `distributionSha256Sum`.
4. Review `build/libs/`. Do not call the mod tested until the game loads and the content is exercised.

No existing Minecraft launcher installation is needed to compile, but network access is needed on initial Gradle resolution.

Your idea: {spec.idea}
""")
    put("fabric-profile.lock.json", json.dumps(p, indent=2) + "\n")
    java_dir = "src/main/java/" + spec.package.replace(".", "/")
    # Mojang official mappings (1.21.1). Yarn names differ; keep this table in one place.
    lines = [
        f"package {spec.package};", "",
        "import net.fabricmc.api.ModInitializer;",
        "import net.fabricmc.fabric.api.itemgroup.v1.ItemGroupEvents;",
        "import net.minecraft.core.Registry;",
        "import net.minecraft.core.registries.BuiltInRegistries;",
        "import net.minecraft.resources.ResourceLocation;",
        "import net.minecraft.world.item.BlockItem;",
        "import net.minecraft.world.item.CreativeModeTabs;",
        "import net.minecraft.world.item.Item;",
        "import net.minecraft.world.level.block.Block;",
        "import net.minecraft.world.level.block.state.BlockBehaviour;",
    ] + [f"import {i};" for i in main_registrations(spec)[0]] + [f"import {i};" for i in gear_registrations(spec)[0]] + ([
        "import net.fabricmc.fabric.api.itemgroup.v1.FabricItemGroup;",
        "import net.minecraft.core.registries.Registries;",
        "import net.minecraft.network.chat.Component;",
        "import net.minecraft.resources.ResourceKey;",
        "import net.minecraft.world.item.CreativeModeTab;",
        "import net.minecraft.world.item.ItemStack;",
    ] if spec.tab else []) + [
        "",
        "public class ModMain implements ModInitializer {",
        f'    public static final String MOD_ID = "{spec.mod_id}";',
        "",
        "    private static ResourceLocation id(String path) {",
        "        return ResourceLocation.fromNamespaceAndPath(MOD_ID, path);",
        "    }",
        "",
    ]
    for feature in spec.features:
        varname = feature.identifier.upper()
        if feature.kind == "item":
            lines.append(f'    public static final Item {varname} = Registry.register(BuiltInRegistries.ITEM, id("{feature.identifier}"), new Item(new Item.Properties()));')
        else:
            lines.append(f'    public static final Block {varname} = Registry.register(BuiltInRegistries.BLOCK, id("{feature.identifier}"), new Block(BlockBehaviour.Properties.of().strength(3.0F)));')
            lines.append(f'    public static final Item {varname}_ITEM = Registry.register(BuiltInRegistries.ITEM, id("{feature.identifier}"), new BlockItem({varname}, new Item.Properties()));')
    mob_imports, mob_fields, mob_init = main_registrations(spec)
    lines += mob_fields
    gear_imports, gear_fields, gear_init = gear_registrations(spec)
    if gear_fields:
        lines += ["", "    // Tools, armor and food (generated from materials/foods in the spec)"] + gear_fields
    def item_const(feature):
        return feature.identifier.upper() + ("_ITEM" if feature.kind == "block" else "")
    if spec.tab:
        icon = next((f for f in spec.features if f.identifier == spec.tab_icon), spec.features[0] if spec.features else None)
        icon_expr = f"new ItemStack({item_const(icon)})" if icon else f"new ItemStack({spec.mobs[0].identifier.upper()}_SPAWN_EGG)"
        lines += ["",
                  f'    public static final ResourceKey<CreativeModeTab> TAB_KEY = ResourceKey.create(Registries.CREATIVE_MODE_TAB, id("{tab_id(spec)}"));',
                  "    public static final CreativeModeTab TAB = FabricItemGroup.builder()",
                  f"        .icon(() -> {icon_expr})",
                  f'        .title(Component.translatable("itemGroup.{spec.mod_id}.{tab_id(spec)}"))',
                  "        .displayItems((params, output) -> {"]
        for feature in spec.features:
            lines.append(f"            output.accept({item_const(feature)});")
        for m in spec.mobs:
            lines.append(f"            output.accept({m.identifier.upper()}_SPAWN_EGG);")
        for gid in gear_item_ids(spec):
            lines.append(f"            output.accept({gid.upper()});")
        lines += ["        })", "        .build();"]
    lines += ["", "    @Override", "    public void onInitialize() {"]
    if spec.tab:
        lines.append("        Registry.register(BuiltInRegistries.CREATIVE_MODE_TAB, TAB_KEY, TAB);")
    lines += mob_init
    lines += gear_init
    for feature in spec.features:
        group = "BUILDING_BLOCKS" if feature.kind == "block" else "INGREDIENTS"
        lines.append(f"        ItemGroupEvents.modifyEntriesEvent(CreativeModeTabs.{group}).register(entries -> entries.accept({item_const(feature)}));")
    lines += ["    }", "}"]
    put(f"{java_dir}/ModMain.java", "\n".join(lines) + "\n")
    put("src/main/resources/fabric.mod.json", json.dumps({
        "schemaVersion": 1, "id": spec.mod_id, "version": "${version}", "name": spec.name,
        "description": "Generated Fabric starter from a user idea", "environment": "*",
        "entrypoints": {"main": [spec.package + ".ModMain"], **({"client": [spec.package + ".client.ModClient"]} if spec.mobs else {})},
        "depends": {"fabricloader": ">=" + p["fabric_loader"], "minecraft": "~1.21.1", "java": ">=21", "fabric-api": "*",
                    **({"geckolib": ">=4.7"} if spec.mobs else {})},
        "license": "ARR",
    }, indent=2) + "\n")
    res = f"src/main/resources/assets/{spec.mod_id}"
    put("src/main/resources/pack.mcmeta", json.dumps({"pack": {"pack_format": 34, "description": spec.name + " assets"}}, indent=2) + "\n")
    lang = {}
    for feature in spec.features:
        key = feature.identifier
        lang[f"{'block' if feature.kind == 'block' else 'item'}.{spec.mod_id}.{key}"] = feature.label
        if feature.kind == "item":
            put(f"{res}/models/item/{key}.json", json.dumps({"parent": "item/generated", "textures": {"layer0": f"{spec.mod_id}:item/{key}"}}, indent=2) + "\n")
            put(f"{res}/textures/item/{key}.png", feature_texture(spec, feature))
        else:
            put(f"{res}/blockstates/{key}.json", json.dumps({"variants": {"": {"model": f"{spec.mod_id}:block/{key}"}}}, indent=2) + "\n")
            put(f"{res}/models/block/{key}.json", json.dumps({"parent": "block/cube_all", "textures": {"all": f"{spec.mod_id}:block/{key}"}}, indent=2) + "\n")
            put(f"{res}/models/item/{key}.json", json.dumps({"parent": f"{spec.mod_id}:block/{key}"}, indent=2) + "\n")
            put(f"{res}/textures/block/{key}.png", feature_texture(spec, feature))
            drop = next((d for d in spec.drops if d.block == key), None)
            put(f"src/main/resources/data/{spec.mod_id}/loot_table/blocks/{key}.json", json.dumps(loot_table_json(spec, key, drop), indent=2) + "\n")
    for m in spec.materials:
        put(f"{java_dir}/gear/{gear_cls(m.identifier)}Tier.java", tier_java(spec, m))
        base, acc = material_colors(spec.mod_id + "/" + m.identifier, m.color or None, m.accent or None)
        for kind in m.tools:
            key = f"{m.identifier}_{kind}"
            put(f"{res}/models/item/{key}.json", json.dumps({"parent": "item/handheld", "textures": {"layer0": f"{spec.mod_id}:item/{key}"}}, indent=2) + "\n")
            put(f"{res}/textures/item/{key}.png", tinted_item_png(kind, base, acc))
            lang[f"item.{spec.mod_id}.{key}"] = f"{m.label} {kind.capitalize()}"
        for kind in m.armor:
            key = f"{m.identifier}_{kind}"
            put(f"{res}/models/item/{key}.json", json.dumps({"parent": "item/generated", "textures": {"layer0": f"{spec.mod_id}:item/{key}"}}, indent=2) + "\n")
            put(f"{res}/textures/item/{key}.png", tinted_item_png("ingot" if kind in ("chestplate", "leggings") else "gem", base, acc))
            lang[f"item.{spec.mod_id}.{key}"] = f"{m.label} {kind.capitalize()}"
        if m.armor:
            put(f"{res}/textures/models/armor/{m.identifier}_layer_1.png", armor_layer_png(1, base, acc, tuple(m.armor)))
            put(f"{res}/textures/models/armor/{m.identifier}_layer_2.png", armor_layer_png(2, base, acc, tuple(m.armor)))
    for f in spec.foods:
        base, acc = material_colors(spec.mod_id + "/" + f.identifier, f.color or None)
        put(f"{res}/models/item/{f.identifier}.json", json.dumps({"parent": "item/generated", "textures": {"layer0": f"{spec.mod_id}:item/{f.identifier}"}}, indent=2) + "\n")
        put(f"{res}/textures/item/{f.identifier}.png", tinted_item_png("food", base, acc))
        lang[f"item.{spec.mod_id}.{f.identifier}"] = f.label
    for recipe in list(spec.recipes) + gear_recipes(spec):
        put(f"src/main/resources/data/{spec.mod_id}/recipe/{recipe.id}.json", json.dumps(recipe_json(spec, recipe), indent=2) + "\n")
        put(f"src/main/resources/data/{spec.mod_id}/advancement/recipes/{recipe.id}.json", json.dumps(recipe_advancement_json(spec, recipe), indent=2) + "\n")
    if spec.tab:
        lang[f"itemGroup.{spec.mod_id}.{tab_id(spec)}"] = spec.tab
    if spec.mobs:
        put(f"{java_dir}/client/ModClient.java", client_init_java(spec))
        for m in spec.mobs:
            put(f"{java_dir}/entity/{class_name(m)}Entity.java", entity_java(spec, m))
            put(f"{java_dir}/client/{class_name(m)}Renderer.java", renderer_java(spec, m))
            put(f"{res}/geo/entity/{m.identifier}.geo.json", json.dumps(placeholder_geo(m), indent=2) + "\n")
            put(f"{res}/animations/entity/{m.identifier}.animation.json", json.dumps(placeholder_animation(m), indent=2) + "\n")
            put(f"{res}/textures/entity/{m.identifier}.png", placeholder_png(spec.mod_id + "/entity/" + m.identifier, 64, 32))
            put(f"src/main/resources/data/{spec.mod_id}/loot_table/entities/{m.identifier}.json", json.dumps(entity_loot(spec, m), indent=2) + "\n")
            # vanilla egg model: two tinted layers coloured from the SpawnEggItem constructor
            put(f"{res}/models/item/{m.identifier}_spawn_egg.json", json.dumps({"parent": "minecraft:item/template_spawn_egg"}, indent=2) + "\n")
            lang[f"entity.{spec.mod_id}.{m.identifier}"] = m.label
            lang[f"item.{spec.mod_id}.{m.identifier}_spawn_egg"] = f"{m.label} Spawn Egg"
    put(f"{res}/lang/en_us.json", json.dumps(lang, indent=2, sort_keys=True) + "\n")
    manifest = {"generator": "mod-orchestra 0.1.0", "generator_version": GENERATOR_VERSION, "status": "GENERATED_UNVERIFIED", "profile": p["id"], "files": written.copy(), "build_verified": False, "runtime_verified": False}
    put(".mod-orchestra/generation-manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"path": str(directory), "files": len(written), "status": "GENERATED_UNVERIFIED", "manifest": str(directory / ".mod-orchestra/generation-manifest.json")}


def feature_texture(spec: Spec, feature) -> bytes:
    """Tinted silhouette for a simple item/block (own masks, stable colour per identifier unless chosen)."""
    shape = feature.shape or ("block" if feature.kind == "block" else "gem")
    base, acc = material_colors(spec.mod_id + "/" + feature.identifier, feature.color or None)
    return tinted_item_png(shape, base, acc)


def tab_id(spec: Spec) -> str:
    return f"{spec.mod_id}_tab"


def recipe_json(spec: Spec, r: Recipe) -> dict:
    """Vanilla 1.21.1 recipe JSON (result as an item stack object with `id`)."""
    ids = spec.local_ids()
    result = {"id": resolve_result(ids, spec.mod_id, r.result), "count": r.count}
    if r.kind == "shaped":
        out = {"type": "minecraft:crafting_shaped", "category": "misc", "pattern": list(r.pattern),
               "key": {sym: resolve_ingredient(ids, spec.mod_id, ing) for sym, ing in r.key.items()}, "result": result}
    elif r.kind == "shapeless":
        out = {"type": "minecraft:crafting_shapeless", "category": "misc",
               "ingredients": [resolve_ingredient(ids, spec.mod_id, ing) for ing in r.ingredients], "result": result}
    else:
        out = {"type": f"minecraft:{r.kind}", "category": "misc", "ingredient": resolve_ingredient(ids, spec.mod_id, r.ingredients[0]),
               "result": {"id": result["id"]}, "experience": r.experience, "cookingtime": r.cooking_time}
    if r.group:
        out["group"] = r.group
    return out


def _recipe_inputs(spec: Spec, r: Recipe) -> list[str]:
    ids = spec.local_ids()
    raw = list(r.key.values()) if r.kind == "shaped" else list(r.ingredients)
    out = []
    for ing in raw:
        obj = resolve_ingredient(ids, spec.mod_id, ing)
        if "item" in obj and obj["item"] not in out:
            out.append(obj["item"])
    return out


def recipe_advancement_json(spec: Spec, r: Recipe) -> dict:
    """Unlock advancement so the recipe shows in the recipe book once the player has any input item."""
    inputs = _recipe_inputs(spec, r)
    rid = f"{spec.mod_id}:{r.id}"
    criteria = {"has_the_recipe": {"trigger": "minecraft:recipe_unlocked", "conditions": {"recipe": rid}}}
    requirement = ["has_the_recipe"]
    if inputs:
        criteria["has_input"] = {"trigger": "minecraft:inventory_changed", "conditions": {"items": [{"items": inputs}]}}
        requirement.append("has_input")
    return {"parent": "minecraft:recipes/root", "criteria": criteria, "requirements": [requirement], "rewards": {"recipes": [rid]}}


def loot_table_json(spec: Spec, block_key: str, drop: Drop | None) -> dict:
    """Drop-self by default; with a Drop rule, the vanilla ore shape: silk touch -> block, else item with
    optional count range, Fortune (ore_drops) and explosion decay."""
    self_id = f"{spec.mod_id}:{block_key}"
    if drop is None:
        return {"type": "minecraft:block", "pools": [{"rolls": 1, "entries": [{"type": "minecraft:item", "name": self_id}],
                                                      "conditions": [{"condition": "minecraft:survives_explosion"}]}]}
    item_id = resolve_result(spec.local_ids(), spec.mod_id, drop.item)
    functions = []
    if (drop.count_min, drop.count_max) != (1, 1):
        functions.append({"function": "minecraft:set_count", "count": {"type": "minecraft:uniform", "min": drop.count_min, "max": drop.count_max}})
    if drop.fortune:
        functions.append({"function": "minecraft:apply_bonus", "enchantment": "minecraft:fortune", "formula": "minecraft:ore_drops"})
    functions.append({"function": "minecraft:explosion_decay"})
    item_entry = {"type": "minecraft:item", "name": item_id, "functions": functions}
    if not drop.silk_touch:
        return {"type": "minecraft:block", "pools": [{"rolls": 1, "entries": [item_entry]}]}
    silk_entry = {"type": "minecraft:item", "name": self_id, "conditions": [{"condition": "minecraft:match_tool", "predicate": {
        "predicates": {"minecraft:enchantments": [{"enchantments": "minecraft:silk_touch", "levels": {"min": 1}}]}}}]}
    return {"type": "minecraft:block", "pools": [{"rolls": 1, "entries": [{"type": "minecraft:alternatives", "children": [silk_entry, item_entry]}]}]}


def verified_wrapper_file(relative: str, expected_sha256: str) -> bytes:
    """Read an embedded wrapper file and refuse it if its bytes drifted from PROVENANCE.md."""
    source = WRAPPER_DIR / relative
    if not source.is_file():
        raise StateError(f"Embedded Gradle wrapper file missing from install: {relative}")
    data = source.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise StateError(f"Embedded Gradle wrapper {relative} hash {actual[:12]} != recorded {expected_sha256[:12]}; refusing to ship it")
    return data


def workspace_generation_info(path: Path) -> dict:
    """Which generator wrote this workspace and whether it ships the wrapper (H3)."""
    manifest_file = path / ".mod-orchestra/generation-manifest.json"
    if not manifest_file.is_file():
        return {"generator_version": None, "has_wrapper": False, "current": GENERATOR_VERSION}
    files = json.loads(manifest_file.read_text(encoding="utf8")).get("files", {})
    version = json.loads(manifest_file.read_text(encoding="utf8")).get("generator_version", 1)
    return {"generator_version": version, "has_wrapper": all(k in files for k in WRAPPER_FILES),
            "current": GENERATOR_VERSION, "outdated": version < GENERATOR_VERSION}


RUNTIME_DIRS = ("run/", "build/", ".gradle/", ".mod-orchestra/", "bin/", "out/")


def is_runtime_path(relative: str) -> bool:
    """Directories the game, Gradle or the controller write to at runtime: never part of the source manifest."""
    rel = relative.replace("\\", "/").lstrip("./")
    return any(rel.startswith(d) for d in RUNTIME_DIRS)


def current_hashes(manifest: dict) -> dict[str, str]:
    """Generation hashes overlaid with every accepted revision, in order; runtime paths are ignored even if an
    older revision recorded them (host run 5: a worker reported run/eula.txt as changed)."""
    files = dict(manifest["files"])
    for rev in manifest.get("revisions", []):
        files.update(rev["files"])
    return {k: v for k, v in files.items() if not is_runtime_path(k)}


def accept_changes(path: Path, *, run_id: str, actor: str, changed: list[str]) -> dict:
    """Record files a worker reported as changed (or added) as a manifest revision attributed to a run.
    Only reported files are re-hashed: anything else that differs stays CHANGED (unreported = tampered)."""
    manifest_file = path / ".mod-orchestra/generation-manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf8"))
    before = current_hashes(manifest)
    files, skipped = {}, []
    for relative in changed:
        relative = relative.replace("\\", "/").lstrip("./")
        if is_runtime_path(relative):
            skipped.append(relative); continue
        try:
            file_path = safe_inside(path, relative)
        except InputError:
            skipped.append(relative); continue
        if not file_path.is_file():
            skipped.append(relative); continue
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if before.get(relative) != digest:
            files[relative] = digest
    if files:
        manifest.setdefault("revisions", []).append({"run": run_id, "actor": actor, "at": time.time(), "files": files})
        manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    return {"accepted": sorted(files), "unchanged_or_missing": skipped}


def validate_generated(path: Path) -> dict:
    manifest_file = path / ".mod-orchestra/generation-manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf8"))
    problems = []
    files = current_hashes(manifest)
    for relative, expected in files.items():
        file_path = safe_inside(path, relative)
        if not file_path.is_file():
            problems.append("MISSING: " + relative)
        elif hashlib.sha256(file_path.read_bytes()).hexdigest() != expected:
            problems.append("CHANGED: " + relative)
        if relative.endswith(".json") and file_path.is_file():
            try:
                json.loads(file_path.read_text(encoding="utf8"))
            except (ValueError, UnicodeDecodeError) as exc:
                problems.append("BAD JSON: " + relative + ": " + str(exc))
    return {"status": "PASS" if not problems else "FAIL", "checked": len(files), "revisions": len(manifest.get("revisions", [])),
            "problems": problems, "note": "Static generation-only check; not a Minecraft build or runtime test"}
