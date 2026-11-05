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
On MODEL tasks the controller places `models/<mob>.bbmodel` already built from the mob's body plan: an empty `root`,
bones with pivots at the joints (two-joint limbs: `left_leg` → `left_leg_shin`), cubes, box UV packed without overlaps,
`animation.<mob>.idle` / `.walk` (loop) and `.attack` (one-shot) valid. Edit it (resize and move cubes, add detail cubes
to existing bones, add child bones such as `left_horn` under `head`, retune the clips with `replace: true`); keep the
bone names so the clip patterns keep applying. Rebuild from scratch with `bbmodel_geckolib_create` only when no plan
fits. Loops keep their seam; one-shots start and end at rest; times on multiples of 0.05.

| plan | texture | bones | how to adapt |
|---|---|---|---|
| `quadruped` | 64x64 | root, body, head, tail, left_front_leg, left_front_leg_lower, left_back_leg, left_back_leg_lower, right_front_leg, right_front_leg_lower, right_back_leg, right_back_leg_lower | Diagonal gait: left_front with right_back, right_front with left_back; the *_lower joints bend one way (knee/hock). `root` is empty: animate it for whole-body moves (slam, collapse) and keep `body` for the torso. Head pivot is the neck, tail pivot the rump. Longer lower legs for deer, longer body for dachshund. Attack: Lunge: rear up (windup 0.3), bite forward with the front legs down (impact 0.5), settle. |
| `biped` | 64x64 | root, body, head, left_arm, left_arm_forearm, left_leg, left_leg_shin, right_arm, right_arm_forearm, right_leg, right_leg_shin | Vanilla humanoid pivots (head 24, shoulders ±5/22, hips ±2/12): armor and held items line up. Elbows at y 18, knees at y 6. Arms swing opposite to the leg on the same side; forearms follow through. Shrink to 3/4 for a child, widen torso for a brute, add a third joint (hand) for a boss. Attack: Overhead right-arm swing: windup 0.3 (arm back, torso twists), impact 0.5 (arm down, torso follows), recovery 0.65, rest 1.0. |
| `bird` | 64x64 | root, body, head, left_wing, right_wing, tail, left_leg, right_leg | Wings pivot at the shoulder on the body's side and flap on Z. Head bobs with each step. For flight, add a fly clip with wings at ±40 on Z; for a big bird scale the body and lengthen the legs. Attack: Peck: head back 0.2, strike down-forward 0.4 with a wing flick, settle by 0.8. |
| `fish` | 64x64 | root, body, head, top_fin, left_fin, right_fin, tail, tail_fin | walk = swim: tail and tail_fin wag on Y with the fin leading more than the tail; body counter-wags. Floats at Y 2-11; the entity hitbox height should match (~0.6). Flatten for a ray, lengthen for an eel. Attack: Bite: a hard tail beat throws the body forward (0.4) as the head snaps down. |
| `serpent` | 64x64 | root, body, head, segment_2, segment_3, tail | Alternating Y-rotation signs down the chain make the S-curve; each segment pivots at its front joint. Add segments by chaining more bones with the same 4-unit step. Raise the head bone for a cobra. Attack: Strike: coil back and rear the head (0.3), lunge forward and down (0.5), recover. |
| `insect` | 64x64 | root, body, head, abdomen, left_front_leg, left_front_leg_lower, left_mid_leg, left_mid_leg_lower, left_back_leg, left_back_leg_lower, right_front_leg, right_front_leg_lower, right_mid_leg, right_mid_leg_lower, right_back_leg, right_back_leg_lower | Tripod gait: front+back of one side move with the middle leg of the other; *_lower joints bend like knees. Legs are 1x2x1 + 1x2x1 under the thorax; splay the upper bones outward (rotation Z ±30) for a spider, drop two legs for a beetle, lengthen the lower segments for a mantis. Attack: Bite: rear up with the front legs raised (0.2), snap the head down (0.4), settle. |

Held item: a biped has an empty `held_item` bone at the right palm (a child of the forearm). When the mob holds something (the task packet says so; by default the best sword/axe/pickaxe/shovel/hoe
among its drops) the entity draws it on that bone, so it follows every arm animation. Keep the bone, keep it at the grip when you reshape or move the arm, and tilt it with its own
rotation if the weapon points the wrong way in the game; `bbmodel_geckolib_validate` passes without cubes there and install fails if the bone is gone.

Pairing rule: a `left_*` bone always has a `right_*` twin with the X of its pivot negated; keep that when adding limbs.
Target density: the base rig is a 10–19 bone skeleton; a finished creature runs 15–35 bones at ~1.5 cubes per bone
(every part that moves on its own gets a bone: ears, jaw, tail segments, props). See the calibration table in
`knowledge/blockbench/formats-java-1.21.1.md` §9.

## Shape and motion rules (from finished boss-scale rigs, §10 of the formats note)
- Rotate cubes for shape, bones for motion: angled shoulder plates, horns, spines and fins are rotated cubes
  (`rotation` on the cube, pivot at its base); only what animates gets a bone. Half the cubes of a good model are rotated.
- A joint bends one way: knees/elbows/hocks use `-amp * max(0, sin)`, never a symmetric swing. Time it with the leg: the knee flexes during the
  forward swing, so the foot leaves the ground only while it travels forward and stays planted while it pushes back (the foot's highest
  point is in the swing). Flexing the knee in the push-off half reads as a leg kicked up behind, i.e. an inverted knee in game.
  `bbmodel_quality_gates` reports `GAIT_PHASE` for any `*_shin` / `*_lower` bone of a walk or run clip that does this.
- One-shot anatomy (attack, eat, roar): windup 25–30% of the clip, impact at 45–55%, a short hold, recovery to rest at
  the end. Windups are big (arms to -110…-150 on X, torso twist 10–20 on Y); impacts carry a body `position` dip of
  1–3 units; child bones (forearm, hand, head) get the same curve 0.05–0.1 s later (follow-through).
- Loops are subtle: idle ±2–5 on rotation, walk ±25–30 on legs, 0.3–0.8 position bob. Decorative bobs on one-shots fade
  in and out (`sin²(πt/length)` envelope) so the clip starts and ends at rest.
- `death`-style clips export `loop: "hold"` (`hold_on_last_frame`); only idle/walk loop.
- Impacts are linear: the windup→impact pair is two `linear` keys 0.1–0.15 s apart (60° in 0.12 s reads as a hit); the
  anticipation before it can be long and smooth (`catmullrom`, 1 s+ for a sneeze or roar) and the recovery adds small
  aftershocks (±6° wobble) before rest. Props launched by the hit get linear position/rotation keys (ballistic arc, spin).
- `scale` is a tool, not a hazard: 1.04/0.96 squash-and-stretch on a chewing head, 1.35 on a puffed tail; 0 on a bone
  hides that part (step it with two linear keys 0.05 s apart) and the validator only warns. Negative scale never.
- A clip may re-pose the whole creature: a biped's walk can drop it on all fours (`body` rotation −90 and a lift on
  position, head compensating, legs stretched by scale). Put stance on `body`, not in the rig.
- Chains (tails, serpents, tentacles): a travelling wave — each segment repeats the previous one a fraction of a cycle
  later with ~1.5× the amplitude, so the tip whips after the base; the idle tail of a creature does a slow figure-8
  (X and Y out of phase) with the tip lagging.
- State clips: `loop: hold` clips that leave a pose (`backpack_off`) paired with a loop that runs in that state
  (`backpack_idle`) make a state machine out of animations; the entity switches controllers by state.
- `root` is the vehicle: a dive, a surfacing, a leap, a death collapse are keys on `root` (pitch on X, position on Y/Z);
  a roll spins `body` under a steady `root`. The rig stays animatable on top.
- Drift every chain, growing distally: a swimmer or flyer at rest sways on `root` (±0.5°) and every tail or fin segment
  wobbles a little more than its parent (2° → 6° to the tip); 8 s cycles for a boss, 2–3 s for a small creature.
  Pectoral fins and wings with several segments are constant-amplitude chains (`grow 1.0`); tails grow 1.3–1.5.
- Sound or strain is vibrato: a small fast oscillation (±1.5° every 0.13 s on the jaw) while the pose holds reads as
  singing, growling, chattering claws, a straining lift.
- Big creatures need big bounds: set `visible_box` to cover the whole model or the renderer culls it when its origin
  leaves the screen; clip lengths scale with size (a 7-block whale: loops 4–8 s, one-shots 3–6 s).
- Rest pose on bones, not cubes, when the shape is a posed limb: a splayed spider leg or a cocked wing is `rotation` on the
  bone (pivot at the joint), so every clip stays relative to the pose and the joint still bends where it should. Rotate
  the cube itself only for static shape (plates, horns, fins) that never animates on its own.
- Joint caps: at a visible bend, a small cube in its own bone at the joint pivot (`left_leg_knee`), animated at about half
  the child's angle, hides the gap between segments.
- Round with `inflate` (shells, bellies, claws, 0.25–1.0) instead of extra cubes; `mirror_uv` on the twin of a paired
  limb so only one side needs painting; a PNG at 2x or 4x the project resolution is accepted (hi-res skin, same UV).
- Alive idle: besides one slow bob, give the head/body/props sub-2° multi-axis drift with different phases per bone and
  an occasional 0.1 s spike (blink, twitch, ear flick); paired parts must not move in sync. Walk limbs lift only during
  their swing half.

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
