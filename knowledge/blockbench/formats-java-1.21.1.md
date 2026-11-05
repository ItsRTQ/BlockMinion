---
id: blockbench.formats.java.1.21.1
status: curated
minecraft: 1.21.1
geckolib: 4.7.3
blockbench_format: 5.0
last_reviewed: 2026-11-04
---

# Blockbench → Minecraft Java formats (1.21.1 profile)

Curated from two research documents RTQ supplied on 2026-11-04 (both LLM-written; every rule below was
checked against `tools/blockbench-mcp-safe/src/*.mjs`, `src/mod_orchestra/resources/blockbench/armor_template.geo.json`
or what `examples/kitchen_sink` compiles). Rules that are **enforced** by the vendored server are marked so;
the rest are conventions the designer must follow by hand. Anything for Minecraft > 1.21.1 lives in the last section
and must not be copied into generated code.

## 1. Coordinates and units

- 1 unit = 1 pixel = 1/16 block. Right-handed: +X east, +Y up, +Z south (toward the camera in front view).
- Entities stand on Y=0; a 1-block-tall mob spans Y 0→16. The vanilla player is 32 high: head pivot `[0,24,0]`,
  arms `[±5,22,0]`, legs `[±1.9,12,0]`.
- `.bbmodel` is `format_version 5.0` (**enforced** by the server). Keyframe values are stored in these same axes.
- The GeckoLib export mirrors X and flips rotation X/Y, exactly like Blockbench's own Bedrock exporter:
  bone `pivot=[-x,y,z]`, `rotation=[-rx,-ry,rz]`, cube `origin=[-to_x,from_y,from_z]`, keyframe rotation
  `[-x,-y,z]`, position `[-x,y,z]`, scale unchanged. **Never compensate for this when authoring**; author in
  Blockbench space and let `bbmodel_geckolib_export_*` do the flip. The CI oracle job compares against upstream.

## 2. Box UV layout (what the texture must cover)

Cube `uv_offset=[u,v]`, size `w=Δx, h=Δy, d=Δz` (floored). Faces occupy, in pixels of the texture:

| face  | from              | to                    |
|-------|-------------------|-----------------------|
| up    | `[u+d, v]`        | `[u+d+w, v+d]`        |
| down  | `[u+d+w, v]`      | `[u+d+2w, v+d]`       |
| east  | `[u, v+d]`        | `[u+d, v+d+h]`        |
| north | `[u+d, v+d]`      | `[u+d+w, v+d+h]`      |
| west  | `[u+d+w, v+d]`    | `[u+2d+w, v+d+h]`     |
| south | `[u+2d+w, v+d]`   | `[u+2d+2w, v+d+h]`    |

One cube therefore needs a strip `(2d+2w) × (d+h)`. Lay cubes out so strips do not overlap and all fit inside
`resolution` (64×64 for every base rig and most creatures with 30–70 cubes; 128 or 256 only for bosses or high-detail skins). Box UV is the only mode the server exports
for cubes; per-face UV with face rotation bumps the geo `format_version` to `1.21.0` (server does this itself).

## 3. GeckoLib geometry and animation (`4.7.3`, Fabric 1.21.1)

- Geometry: `format_version 1.12.0`, `minecraft:geometry[0].description.identifier = geometry.<id>`,
  `texture_width/height` = project resolution, `visible_bounds_*` from `visible_box`. Bones: `name`, optional
  `parent` (string), `pivot`, optional `rotation`, `cubes[]` with `origin`, `size`, `uv`, optional `inflate`,
  `mirror`, and per-cube `pivot`+`rotation` when the cube itself is rotated.
- Asset paths the generated `DefaultedEntityGeoModel` expects: `geo/entity/<id>.geo.json`,
  `animations/entity/<id>.animation.json`, `textures/entity/<id>.png` (armor: `geo/item/armor/<material>.geo.json`,
  `animations/item/armor/<material>.animation.json`, `textures/item/armor/<material>.png`).
- Animation: `format_version 1.8.0`, `animations.<name>` with `loop: true | "hold_on_last_frame"`,
  `animation_length`, `bones.<bone>.{rotation,position,scale}` keyed by time string (`"0.0"`, `"0.5"`).
  Keyframes `[x,y,z]` numeric; `lerp_mode: catmullrom` and easings are allowed. Molang strings are accepted by
  GeckoLib but the server only writes numeric keyframes.
- Names the entity class plays: exactly `animation.<id>.idle` and `animation.<id>.walk`
  (**enforced** by `bbmodel_geckolib_validate {require_idle_walk:true}`).
- Unsupported on export (**enforced**): meshes, `bedrock_binding`, `mirror_uv`, hidden/unexported groups,
  keyframes with more than one data point. Generic (`free`) models can hold meshes but cannot export to GeckoLib.
- Locators are not emitted by the server today; `particle_effects` / `sound_effects` keyframes are a backlog item.

## 4. GeckoLib armor bones (`GeoArmorRenderer`)

Root bones must carry these exact names; the renderer copies the wearer's limb pose onto them and shows only the
bones of the slot being rendered. Pivots in Blockbench space, as in `armor_template.bbmodel`
(the `.geo.json` shows them X-mirrored, e.g. `armorRightArm` → `[5,22,0]`):

| bone            | follows                   | slot  | pivot (bb)     |
|-----------------|---------------------------|-------|----------------|
| `armorHead`     | `HumanoidModel.head`      | HEAD  | `[0,24,0]`     |
| `armorBody`     | `HumanoidModel.body`      | CHEST | `[0,24,0]`     |
| `armorRightArm` | `HumanoidModel.rightArm`  | CHEST | `[-5,22,0]`    |
| `armorLeftArm`  | `HumanoidModel.leftArm`   | CHEST | `[5,22,0]`     |
| `armorRightLeg` | `HumanoidModel.rightLeg`  | LEGS  | `[-1.9,12,0]`  |
| `armorLeftLeg`  | `HumanoidModel.leftLeg`   | LEGS  | `[1.9,12,0]`   |
| `armorRightBoot`| `HumanoidModel.rightLeg`  | FEET  | `[-1.9,12,0]`  |
| `armorLeftBoot` | `HumanoidModel.leftLeg`   | FEET  | `[1.9,12,0]`   |

Extra geometry (crest, pauldrons, tassets, wings) goes in **child** bones of one of these eight; a free-floating
root bone never moves with the player. Any `.animation.json` on armor bones is additive on top of the limb pose.
Vanilla inflate reference: inner layer (leggings) `0.5`, outer layer `1.0`.

## 5. Vanilla `java_block` models (3D items and blocks) — 1.21.1 rules

`assets/<ns>/models/block|item/<name>.json`. Loaded by `BlockModel`/`BlockElement` deserializers, which **throw**
on any violation and leave the model as the purple/black missing texture:

- `elements[].from/to` each component in `[-16, 32]` (a 3×3×3-block envelope around the cell).
- `elements[].rotation` is optional; when present: one `axis` (`x|y|z`), `angle` in
  `{-45, -22.5, 0, 22.5, 45}`, `origin`, optional `rescale` (scales the two other axes by `1/cos(angle)`:
  ×1.0824 at 22.5°, ×1.4142 at 45°, so diagonal cubes stay seam-free). Free rotation is **not** available in
  1.21.1; needs multiple elements or GeckoLib.
- Faces: `uv [u1,v1,u2,v2]` in 0–16 texture space (Blockbench normalises from the project resolution),
  `texture "#key"`, optional `rotation 0|90|180|270`, `cullface`, `tintindex`.
- `textures` keys are free strings; `particle` should be set. `gui_light: side` for blocks, `front` for flat items.
- `groups[]` in the JSON is Blockbench metadata; Minecraft ignores it. No bone animation exists in this format:
  animation is `.png.mcmeta` texture strips or model swapping.
- `display` per context, `rotation` degrees, `translation` clamped to `±80` (÷16 at load → ±5 blocks),
  `scale` clamped to `±4`. Contexts: `thirdperson_righthand/lefthand`, `firstperson_righthand/lefthand`,
  `gui`, `ground`, `head`, `fixed`.

Vanilla display presets (copy, then adjust):

| context                | handheld (`item/handheld`)                 | block in hand (`block/block`)                |
|------------------------|--------------------------------------------|----------------------------------------------|
| thirdperson_righthand  | rot `[0,-90,55]` tr `[0,4,0.5]` sc `0.85`  | rot `[75,45,0]` tr `[0,2.5,0]` sc `0.375`    |
| thirdperson_lefthand   | rot `[0,90,-55]` tr `[0,4,0.5]` sc `0.85`  | rot `[75,45,0]` tr `[0,2.5,0]` sc `0.375`    |
| firstperson_righthand  | rot `[0,-90,25]` tr `[1.13,3.2,1.13]` sc `0.68` | rot `[0,45,0]` sc `0.40`                |
| firstperson_lefthand   | rot `[0,90,-25]` tr `[1.13,3.2,1.13]` sc `0.68` | rot `[0,225,0]` sc `0.40`               |
| gui                    | (inherits generated flat item)             | rot `[30,225,0]` sc `0.625`                  |
| ground                 | tr `[0,2,0]` sc `0.5`                      | tr `[0,3,0]` sc `0.25`                       |
| fixed                  | sc `0.5`                                   | sc `0.5`                                     |

Third person pipeline: the item is rendered in the arm's `ModelPart` space (`translateToHand`), then the hardcoded
`-90° X, 180° Y, translate (±1/16, 0.125, -0.625)` to reach the grip, then the JSON `display` transform. First
person is a separate procedural renderer (swing/equip/use animations) plus the `firstperson_*` display. So a 3D
sword whose blade points +Y in Blockbench with handle at the origin lands in the hand with the handheld preset.

GeckoLib 3D items on 1.21.1: `models/item/<id>.json` keeps `display` but uses `"parent": "builtin/entity"` and the
mod registers a `GeoItemRenderer` through Fabric's `BuiltinItemRendererRegistry`; without the parent the item is
invisible in hand and GUI.

## 6. Authoring rules for rigs (designer)

- Cubes only; one cube belongs to exactly one bone; bones move rigidly (no skinning anywhere in Java).
  (**enforced**: `GeckoLib cubes require group_uuid`, meshes rejected in `geckolib_model`.)
- Bone names unique, `^[A-Za-z_][A-Za-z0-9_]{0,63}$`, snake_case (**enforced** on `add_group`).
  Use `left_`/`right_` prefixes for paired limbs so a mirrored limb can be generated from its partner.
- One root bone (`body` for quadrupeds, `root` or `body` for bipeds) so whole-model bob/turn is one channel.
- Multi-joint limbs nest proximal → distal (`upper_leg → lower_leg → foot`); the pivot of each bone sits at the
  joint it rotates around, set **before** animating. Wrong pivots show as sliding/floating on rotation.
- Rotation keyframes in degrees, `[-360, 360]` (**enforced**); scale never ≤ 0; looping clips must start and end
  on the same value per channel (**enforced**: `LOOP_SEAM`). `snapping` is 20/s (**enforced**) so keyframes land
  on ticks: use times that are multiples of 0.05.
- Bone density: every cube that should move on its own (ears, jaw, tail segments, a hat, a held prop) gets its own bone;
  finished community creatures run 15–35 bones (bosses 35–55) at ~1.5 cubes per bone. The base rigs are skeletons
  (6–9 bones) to grow from, not a target. `bbmodel_quality_gates` allows 96 bones / 256 cubes.
- Preview before export: `bbmodel_render` at rest and at `walk` time 0.25/0.5; `bbmodel_quality_gates` for the
  numeric gates (UV coverage, proportions, seam checks).

## 7. Validation checklist (what each symptom means)

1. Mob upside-down or sunk into the floor → Y not at feet level, or coordinates hand-mirrored before export.
2. Limbs explode / spin faster every second → keyframes accumulate: a clip without a loop seam, or a controller
   that never resets (`AnimationController` + `RawAnimation.begin().thenLoop(...)` handles this in GeckoLib).
3. Purple/black item or block → a `java_block` element outside `[-16,32]`, an `angle` not in the 22.5° set, or a
   face `texture` key missing from `textures`.
4. Armor stands still while the player walks → root bone names differ from the eight in §4, or geometry sits in a
   root bone that is not one of them.
5. 3D item invisible in hand/GUI → missing `"parent": "builtin/entity"` or no `BuiltinItemRendererRegistry` entry.
6. Texture looks shifted on one face → cube strip overlaps a neighbour's strip (§2), or `resolution` differs from
   the PNG size.

## 8. Not applicable to this profile (do not generate)

- `assets/<ns>/items/<id>.json` client item definitions, `minecraft:item_model` component, `hand_animation_on_swap`:
  1.21.4+. On 1.21.1 use `models/item/<id>.json` with `overrides[].predicate.custom_model_data`.
- `EntityModel<EntityRenderState>` / `setupAnim(state)` / `EquipmentClientInfo`: 1.21.2+. The 1.21.1 vanilla
  signature is `EntityModel<T extends Entity>` with `setupAnim(T, limbSwing, limbSwingAmount, ageInTicks, netHeadYaw,
  headPitch)`; mobs here use GeckoLib and never hand-write `LayerDefinition`s.
- Free `java_block` rotation (reported for 1.21.6+; the two sources disagree, irrelevant here).
- OptiFine CEM `.jem/.jpm`, Animated Java display-entity rigs, Easy Model Entities, armatures/weight painting:
  other runtimes or non-exporting features. Migration notes for 1.21.4+ are tracked in `docs/V2_BACKLOG.md`.

## 9. Calibration — what finished community GeckoLib creatures look like (stats only, 2026-11-04)

Read from public model pages on blockbenchworkshop.com; no geometry or files were taken. Use the numbers to judge
whether a model is "done", not as something to copy.

| creature (plan) | cubes | bones | cubes/bone | texture | clips |
|---|---|---|---|---|---|
| white unicorn (quadruped) | 54 | 33 | 1.6 | 256² | 1 (gallop) |
| raccoon merchant (biped) | 29 | 19 | 1.5 | 64² | 13 (idle, sit/beg, eat, walk, run, wash, sneeze, backpack on/off/open/close/idle, happy) |
| cosmic whale (fish, boss) | 55 | 37 | 1.5 | 256² | 6 (drift, swim, sing, roll, dive, emerge) |
| crab captain (insect-like) | 72 | 54 | 1.3 | 64² | 8 (idle, walk, dance, drink, salute, snap, tipsy, hat toss) |
| **base rigs here** | 7–15 | 10–19 | ~0.8 | 64² | 3 (idle, walk, attack) |

What the gap says: (a) legs with 2–3 articulated segments and props on their own bones are where the bone count
comes from; (b) 64×64 is enough for 30–70 cubes when the UV is packed; (c) a creature with personality has
6–13 clips, most of them short one-shot actions on top of idle/walk/run.

## 10. Calibration — a boss-scale rig built programmatically (MeherBenSalem/Bosses, Apache-2.0, read 2026-11-04)

`docs/models/hollow_sovereign` in that repository is a GeckoLib boss authored through a Blockbench MCP from Python,
the same shape as this project's pipeline. Numbers and patterns only; nothing copied.

- 106 cubes, 24 bones, depth 5. Empty `root` at `[0,0,0]` → `body` → `chest` → `head` → `jaw`; `crown` with five shard
  bones on a pentagon of pivots; arms `arm → forearm → hand` (3 joints), legs `leg → shin` (2); tassets as bones.
- 64 of 106 cubes carry per-cube rotation (organic silhouette without extra bones); no `inflate`; per-face UV on a
  512² atlas reusing an existing texture's patches.
- Naming matches ours: `right_*` at −X, `left_*` at +X.
- 9 clips: idle 4 s, walk 1.2 s (loops); awaken, roar, claw_combo 1.8 s (impacts 0.55 and 1.15, second arm delayed
  0.6 s), ground_slam 2.2 s (windup to 0.8, impact 1.05, hold to 1.35), core_blast, enrage (once); death 3.5 s (hold).
- Authoring: 3–6 points per bone (windup → impact → recovery → rest) in a motion module, then a shape-preserving cubic
  (Fritsch–Carlson tangents, zero at peaks) sampled at 24 fps into linear keyframes — portable, runtime-independent;
  7.5k keys. Walk shins use `−28·max(0, sin)`; crown shards bob with a `sin²` envelope on one-shots.
- Amplitudes: rotation −150…+360 (windups), position ±13 (boss scale), scale 0–1.6 (pulsing core).
- Its verifier checks: unique bones, one root, acyclic parents, finite keyframe values, keys within clip length, positive
  cube sizes, every UV rectangle inside the atlas and opaque. `models.validate_model_files` now checks one root, acyclic
  parents, key timing and box-UV bounds; UV opacity against the PNG is still a backlog item.

