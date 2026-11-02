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

## Rig cheat sheet (quadruped, 64x32)
body [-4,6,-6]→[4,12,6] pivot [0,6,0]; head [-3,12,-10]→[3,16,-6] pivot [0,12,-6]; legs 2×6×2 at x=±3, z=±4, pivot at the hip (y=6). Walk: front-left and back-right legs rotate +20→−20→+20 on X over 1 s, the other pair opposite. Idle: head rotation 0→3→0 over 2 s, optional body position bob 0→0.5→0 with `easeInOutSine`.

## Report
`changed_files`: `models/<mob>.bbmodel`, `models/<mob>.geo.json`, `models/<mob>.animation.json`, `models/<mob>.png`. `checks_run`: the validate call and its result. Evidence level `STATIC` (the controller installs and the user verifies in-game).

## Worn-armor preview (ARMOR tasks)
`models/<material>_armor.bbmodel` is a player template (head, body, arms, legs; box UV at the classic 64x32 armor
layout; inflate 1). Do not edit its geometry. Paint `models/sprites/<material>_layer_1.png` / `_layer_2.png`, then
`bbmodel_geckolib_set_texture {file: "<material>_armor.bbmodel", png_file: "sprites/<material>_layer_1.png"}` and
`bbmodel_render {file, output_file: "<material>_armor_layer1.png", overwrite: true}`; repeat for layer 2. The render
shows front/right/back/iso: if the face is covered, a region is shifted, or it reads flat, fix the PNG and render again.
Edges: soft gradient steps 15–20% darker than the fill, never black outlines; adjacent faces of one piece share edge colour.
