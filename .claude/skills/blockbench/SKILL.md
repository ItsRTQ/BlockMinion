---
name: blockbench
description: Author a GeckoLib mob model (.bbmodel, geo.json, animation.json, texture) with the vendored blockbench-mcp-safe MCP server. Use on MODEL tasks or whenever a Blockbench model, rig, animation or mob texture is needed.
---

# Blockbench / GeckoLib authoring with `blockbench-mcp-safe` (v0.5.1)

Server root is `models/` in the workspace; only top-level files; writes need the server started with
`--allow-write` (the controller does). Every write returns a `revision` (SHA-256 of the file) and the next
write must pass it as `expected_revision`. Tool names are `mcp__blockbench__<name>`.

## Flow (in this order)
1. `bbmodel_geckolib_create {file:"<mob>.bbmodel", name, identifier:"<mob>", modid:"<mod_id>", model_type:"Entity", texture_width:64, texture_height:32}`
2. `bbmodel_edit {file, expected_revision, operations:[...]}` — bones first, then cubes:
   - `{"op":"add_group","name":"body","origin":[0,6,0]}` → returns `changes[].uuid`
   - `{"op":"add_group","name":"head","parent_group_uuid":<body uuid>,"origin":[0,12,-6]}`
   - `{"op":"add_cube","name":"body_cube","group_uuid":<uuid>,"from":[-4,6,-6],"to":[4,12,6],"uv_offset":[0,0]}` (`mirror:true`, `inflate` optional)
   Coordinates are Blockbench units (16 = one block); y up; pivots (`origin`) are what animations rotate around.
3. Texture: write a PNG into `models/<mob>.png` with the model resolution (box UV: each cube occupies a strip starting at its `uv_offset`), then `bbmodel_geckolib_set_texture {file, expected_revision, png_file:"<mob>.png"}`.
4. Animations: `bbmodel_geckolib_upsert_animation {file, expected_revision, name:"animation.<mob>.idle", length:2, loop:"loop", channels:[{bone, channel:"rotation"|"position"|"scale", keyframes:[{time, value:[x,y,z], interpolation?}]}]}`; same for `animation.<mob>.walk` (length 1). Re-running on an existing clip needs `replace:true` (and `replace_tracks:false` to merge). Easing values: `linear`, `catmullrom`, `easeInOutSine`, …
5. `bbmodel_geckolib_validate {file, require_idle_walk:true}` must return `valid:true`.
6. Look at it: `bbmodel_render {file, output_file:"<mob>_rest.png", overwrite:true}` and `{..., animation:"animation.<mob>.walk", time:0.5, output_file:"<mob>_walk.png"}`; fix proportions if it looks wrong. `bbmodel_sample_pose {file, animation, time}` gives the numbers.
7. Export: `bbmodel_geckolib_export_geometry {file, output_file:"<mob>.geo.json", overwrite:true}` and `bbmodel_geckolib_export_animations {file, output_file:"<mob>.animation.json", overwrite:true}`.

## Conventions the exporter applies (do not compensate for them)
X is mirrored on export (Blockbench +X = Bedrock −X) and rotation X/Y signs flip; this matches Blockbench's own Bedrock export. Animation names must be exactly `animation.<mob>.idle` and `animation.<mob>.walk`; the entity class plays them by name.

## Reference
Formats, box-UV strip layout, armor bone table, `java_block` constraints/display presets and the symptom checklist for
this profile are in `knowledge/blockbench/formats-java-1.21.1.md` (`orchestra_knowledge_search "box uv"` finds it).
Authoring rules: cubes only, unique snake_case bone names with `left_`/`right_` prefixes, pivots at the joints before
animating, keyframe times in multiples of 0.05, looping clips end where they start.

## Base rigs (MODEL tasks start from one)
On MODEL tasks the controller places `models/<mob>.bbmodel` already built from the mob's body plan: bones with pivots
at the joints, cubes, box UV packed without overlaps, `animation.<mob>.idle` and `.walk` valid. Edit it (resize and
move cubes, add detail cubes to existing bones, add child bones such as `left_horn` under `head`, retune the clips
with `replace: true`); keep the bone names so the walk/idle patterns keep applying. Rebuild from scratch with
`bbmodel_geckolib_create` only when no plan fits. Every clip must keep its loop seam and times on multiples of 0.05.

| plan | texture | bones | how to adapt |
|---|---|---|---|
| `quadruped` | 64x64 | body, head, tail, left_front_leg, right_front_leg, left_back_leg, right_back_leg | Diagonal gait: left_front with right_back, right_front with left_back. Head pivot is the neck (top-front of body), tail pivot the rump. Scale legs taller for deer, body longer for dachshund. |
| `biped` | 64x64 | body, head, left_arm, right_arm, left_leg, right_leg | Vanilla humanoid pivots (head 24, arms ±5/22, legs ±2/12): armor and held items line up. Arms swing opposite to the leg on the same side. Shrink to 3/4 for a child, widen torso for a brute. |
| `bird` | 64x64 | body, head, left_wing, right_wing, tail, left_leg, right_leg | Wings pivot at the shoulder on the body's side and flap on Z. Head bobs with each step. For flight, add a fly clip with wings at ±40 on Z; for a big bird scale the body and lengthen the legs. |
| `fish` | 64x64 | body, head, top_fin, left_fin, right_fin, tail, tail_fin | walk = swim: tail and tail_fin wag on Y with the fin leading more than the tail; body counter-wags. Floats at Y 2-11; the entity hitbox height should match (~0.6). Flatten for a ray, lengthen for an eel. |
| `serpent` | 64x64 | body, head, segment_2, segment_3, tail | Alternating Y-rotation signs down the chain make the S-curve; each segment pivots at its front joint. Add segments by chaining more bones with the same 4-unit step. Raise the head bone for a cobra. |
| `insect` | 64x64 | body, head, abdomen, left_front_leg, left_mid_leg, left_back_leg, right_front_leg, right_mid_leg, right_back_leg | Tripod gait: front+back of one side move with the middle leg of the other. Legs are 1x4x1 under the thorax; splay them outward (rotation Z ±30 on the bones) for a spider, drop two for a beetle. |

Pairing rule: a `left_*` bone always has a `right_*` twin with the X of its pivot negated; keep that when adding limbs.
Target density: the base rig is a 6–9 bone skeleton; a finished creature runs 15–35 bones at ~1.5 cubes per bone
(every part that moves on its own gets a bone: ears, jaw, tail segments, props). See the calibration table in
`knowledge/blockbench/formats-java-1.21.1.md` §9.

## Report
`changed_files`: `models/<mob>.bbmodel`, `models/<mob>.geo.json`, `models/<mob>.animation.json`, `models/<mob>.png`. `checks_run`: the validate call and its result. Evidence level `STATIC` (the controller installs and the user verifies in-game).

## Worn-armor preview (ARMOR tasks)
`models/<material>_armor.bbmodel` is a player template (head, body, arms, legs; box UV at the classic 64x32 armor
layout; inflate 1). Do not edit its geometry. Paint `models/sprites/<material>_layer_1.png` / `_layer_2.png`, then
`bbmodel_geckolib_set_texture {file: "<material>_armor.bbmodel", png_file: "sprites/<material>_layer_1.png"}` and
`bbmodel_render {file, output_file: "<material>_armor_layer1.png", overwrite: true}`; repeat for layer 2. The render
shows front/right/back/iso: if the face is covered, a region is shifted, or it reads flat, fix the PNG and render again.
Edges: soft gradient steps 15–20% darker than the fill, never black outlines; adjacent faces of one piece share edge colour.

## 3D GeckoLib armor (ARMOR3D tasks)
`models/<material>_armor.bbmodel` is the GeckoLib armor template: bones `armorHead`, `armorBody`, `armorRightArm`,
`armorLeftArm`, `armorRightLeg`, `armorLeftLeg`, `armorRightBoot`, `armorLeftBoot` with vanilla pivots and one base
cube each (64x64 UV). Never rename, re-pivot or delete them; add cubes with `group_uuid` of the bone they belong to
(a crest under armorHead, pauldrons under the arm bones, tassets under armorBody). Export with
`bbmodel_geckolib_export_geometry` → `models/<material>_armor.geo.json` (identifier must stay
`geometry.<material>_armor`) and `bbmodel_geckolib_export_animations` after `bbmodel_geckolib_upsert_animation`
for `animation.<material>_armor.idle` (can be static). Render to `models/<material>_armor_render.png` and look.
