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
3. Texture: do not paint pixels by hand; `mcp__minecraft-orchestra__orchestra_paint_skin {project, mob, palette, zones, surface, face}` paints `models/<mob>.png` from the `.bbmodel` (run it once the cubes are final, and again after any reshape).
   **The colours are never given here and never yours to invent: they come from the task packet** (the creature's art direction: concept, visual cues, `reference`, `avoid`, and the palette taken from the theme). Nothing below carries a colour on purpose; if you catch yourself reaching for a colour out of habit, stop and reread the art direction.
   - `palette`: `{"base": "<the skin, fur or shell colour of the art direction>", "<name>": "<hex>", ...}`, one name per material (cloth, metal, bone, growth ...). Living things are desaturated and uneven in value; at most one saturated accent (eyes, glow, blood).
   - `zones`: `[{"bones": ["<bone or pattern>", ...], "color": "<palette name>", "surface": "<preset>"}]`; the first match wins, `*` is allowed, unmatched bones use `base`. Skin, cloth and armour are different zones.
   - `surface` (what the material looks like up close; per zone, or for the whole skin): `flesh` (skin: uneven tone, thin veins, a few marks), `rotten` (diseased: strong mottling, dark veins, growths, sores), `hide` (fur and leather: streaks and scuffs), `cloth` (rags: thread, stains, holes, dirt rising from the hem), or an object `{preset, mottle, veins, blotches, scars, grime, streaks, weave, tears, ramp}` (numbers 0-1; scars and tears 0-8). Every extra colour is derived from the zone's own, so a surface never brings a hue of its own, and shadows lean cold and lights warm. A zone without a surface is for things that really are flat (a painted shield).
   - No regular bands or stripes unless the art direction asks for stripes: they read as a toy. (`bands` exists for that case.)
   - `face`: `{"style": "angry"|"calm"|"grim", "eyes", "mouth", "brow", "teeth", "nose", "tusks"}`. `grim` is small deep-set eyes in dark sockets under a heavy brow with a ragged mouth: use it for anything grotesque, diseased or menacing. `angry` and `calm` have bigger, brighter eyes and read as characters. Colours are pushed apart from what surrounds them (eyes light against their socket and the skin, mouths and brows dark); `adjusted` lists what changed.
   - Shape comes before paint: if the art direction says hulking, massive or top-heavy, change the cubes first (thick shoulders and arms, a small head). No texture turns a slender mascot into a brute.
   - The art direction can carry a `reference` (a creature or character it should resemble) and an `avoid` list (cartoon, saturated, striped ...): honour both over every default in this file.
   - It writes a 2x skin (128x128 over a 64x64 layout) so the face has 16x16 pixels; `scale: 1` keeps 64x64, `4` gives 256x256. Faces on other cubes (a snout, a beak, a visor) are painted on top by hand after, with colours far from their surroundings.
   - The result carries `face_check` (`ok`, `features` = separate dark/bright shapes: two eyes and a mouth make 3, `spread`). Fix until `ok` is true; `orchestra_check_skin {project, mob}` measures any PNG, hand-painted ones included.
   Then `bbmodel_geckolib_set_texture {file, expected_revision, png_file:"<mob>.png"}` (the PNG may be the model resolution or an integer multiple of it) and look at it with `bbmodel_render`: eyes, nose and mouth must be readable at a glance, upright (the north face is the creature's front), and the creature must look like its art direction, not like a toy.
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

## Optional scaffolds (a MODEL task gets one to use, reshape or ignore)
On MODEL tasks the controller places `models/<mob>.bbmodel`, a plain rig for the mob's body plan that already passes the validator: an empty
`root`, bones with pivots at the joints (two-joint limbs: `left_leg` → `left_leg_shin`), box UV packed without overlaps, and
`animation.<mob>.idle` / `.walk` (loop) and `.attack` (one-shot). It exists to save you the technical conventions, not to decide the design.
Use it, reshape it heavily (resize and move cubes, add detail cubes, add child bones such as horns or a tail, retune the clips with
`replace: true`) or ignore it and build your own creature from scratch with `bbmodel_geckolib_create`. Never deliver the scaffold with only a
recolour. Whatever you choose, the game needs: a single empty `root` bone with every other bone under it, the three clips named exactly
`animation.<mob>.idle`, `.walk` and `.attack`, loops that keep their seam, one-shots that start and end at rest, times on multiples of 0.05,
and the validator passing.

**Explore before you build**, the way a painter starts a new piece: write three deliberately different takes on the creature (a different
silhouette, a different signature feature, a different colour story, not three variations of the first idea), avoid its most typical version
unless the description demands it, pick one, and record all three and your choice in the handoff as
`"design_notes": {"takes": ["...", "...", "..."], "chosen": 1, "why": "one sentence"}`. The user sees it and may ask for another take.

| plan | texture | bones | notes on the scaffold (optional) |
|---|---|---|---|
| `quadruped` | 64x64 | root, body, head, tail, left_front_leg, left_front_leg_lower, left_back_leg, left_back_leg_lower, right_front_leg, right_front_leg_lower, right_back_leg, right_back_leg_lower | Diagonal gait: left_front with right_back, right_front with left_back; the *_lower joints bend one way (knee/hock). `root` is empty: animate it for whole-body moves (slam, collapse) and keep `body` for the torso. Head pivot is the neck, tail pivot the rump. Longer lower legs for deer, longer body for dachshund. Attack: Lunge: rear up (windup 0.3), bite forward with the front legs down (impact 0.5), settle. |
| `biped` | 64x64 | root, body, head, left_arm, left_arm_forearm, left_leg, left_leg_shin, right_arm, right_arm_forearm, held_item, right_leg, right_leg_shin | Vanilla humanoid pivots (head 24, shoulders ±5/22, hips ±2/12): armor and held items line up. Elbows at y 18, knees at y 6. Arms swing opposite to the leg on the same side; forearms follow through. The empty `held_item` bone at the right palm carries the weapon the entity holds: keep it, move it to the grip if the hand moves. Shrink to 3/4 for a child, widen torso for a brute, add a third joint (hand) for a boss. Attack: Overhead right-arm swing: windup 0.3 (arm back, torso twists), impact 0.5 (arm down, torso follows), recovery 0.65, rest 1.0. |
| `bird` | 64x64 | root, body, head, left_wing, right_wing, tail, left_leg, right_leg | Wings pivot at the shoulder on the body's side and flap on Z. Head bobs with each step. For flight, add a fly clip with wings at ±40 on Z; for a big bird scale the body and lengthen the legs. Attack: Peck: head back 0.2, strike down-forward 0.4 with a wing flick, settle by 0.8. |
| `fish` | 64x64 | root, body, head, top_fin, left_fin, right_fin, tail, tail_fin | walk = swim: a travelling Y wave down tail → tail_fin (the fin whips most); body counter-wags and `root` sways the whole fish. Whole-body moves (dive, surface, roll) go on `root`; pectoral fins with several segments are constant-amplitude chains. Floats at Y 2-11; the entity hitbox height should match (~0.6). Flatten for a ray, lengthen for an eel. Attack: Bite: a hard tail beat throws the body forward (0.4) as the head snaps down. |
| `serpent` | 64x64 | root, body, head, segment_2, segment_3, tail | A travelling Y wave down the chain (each segment lags the previous one, the tail whips most) makes the slither; each segment pivots at its front joint. Add segments by chaining more bones with the same 4-unit step. Raise the head bone for a cobra. Attack: Strike: coil back and rear the head (0.3), lunge forward and down (0.5), recover. |
| `insect` | 64x64 | root, body, head, abdomen, left_front_leg, left_front_leg_lower, left_mid_leg, left_mid_leg_lower, left_back_leg, left_back_leg_lower, right_front_leg, right_front_leg_lower, right_mid_leg, right_mid_leg_lower, right_back_leg, right_back_leg_lower | Tripod gait: front+back of one side move with the middle leg of the other; *_lower joints bend like knees. Legs are 1x2x1 + 1x2x1 under the thorax; splay the upper bones outward (rotation Z ±30) for a spider, drop two legs for a beetle, lengthen the lower segments for a mantis. Attack: Bite: rear up with the front legs raised (0.2), snap the head down (0.4), settle. |
| `primate` | 64x64 | root, body, head, left_arm, left_arm_lower, left_leg, left_leg_shin, right_arm, right_arm_lower, right_leg, right_leg_shin | Knuckle-walker: the torso is pitched forward by rest rotation on `body` and the head, arms and hands are rotated back to hang from it, so clips stay relative to that pose. The arms are front legs: diagonal gait with the opposite leg, elbows (`*_arm_lower`) flex in the swing like the knees. Attack rears up and slams both arms down. Lengthen the arms for a gorilla, shorten them and stand the torso more upright for a monkey, thicken the head and add a back for a silverback. |

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
