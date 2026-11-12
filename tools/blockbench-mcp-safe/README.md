# Blockbench MCP Safe v0.5.1 — Textures & Animated Pose Preview

**Independent, security-first MCP stdio server**, developed without copying the upstream source of `jasonjgardner/blockbench-mcp-plugin`. It does **not** fetch or execute the upstream repository, install NPM packages, launch Blockbench or open HTTP ports. The optional desktop plugin reads only Blockbench scene data and writes snapshots into the selected workspace.

**Status:** headless GeckoLib authoring subset with **49 automated tests (48 passed and 1 skipped native compatibility fixture)**. **Not validated in a live Blockbench desktop + GeckoLib plugin session or Windows installation**. This is not an exact clone or a drop-in replacement for all original features. Review `SECURITY.md`.

## GeckoLib features and limits

| Feature | Status | Detail |
|---|---|---|
| `.bbmodel` `geckolib_model` | ✅ | Generates Blockbench 5.x-style project container, metadata and model identifier |
| Bone pivots and hierarchies | ✅ | Nested groups, `origin` pivots, rotations, `set_bone_transform`; unique valid bone names |
| Idle and walk animation | ✅ | Numeric `rotation`, `position` and `scale` keyframes; looping/seam checks |
| `.geo.json` | ✅ | Bedrock geometry `1.12.0`, cube UV offsets, origin/rotation X-axis conversions, parents |
| `.animation.json` | ✅ | `1.8.0` format, `geckolib_format_version: 2`, loop modes, numeric keyframes with allowlisted linear, Catmull-Rom and GeckoLib easing |
| GeckoLib validation | ✅ subset | IDs, bones, hierarchy, cube geometry, animation references, loops and UV bounds errors |
| Textures | ✅ subset | `bbmodel_geckolib_set_texture` validates and embeds PNG from `--root`, and assigns all cube face texture UUIDs; a sample checker PNG is provided |
| Complex animation curves | ✅ subset | Linear, Catmull-Rom and selected GeckoLib easing names; no Molang, Bezier handles, effects or controllers |
| Advanced geometry | ⚠️ subset | Generic `.bbmodel` supports triangle/quad meshes; GeckoLib export rejects meshes (Bedrock `poly_mesh` deprecated). Per-face UV cubes export Bedrock `uv_size`, rotations bump output to 1.21.0 |
| `bbmodel_sample_pose` | ✅ local transforms | Samples numeric keyframes, Catmull-Rom, easing, loop wrap. Does not compute inherited world matrices |
| `bbmodel_render` contact sheet | ✅ CPU textured subset | Rasterizes embedded PNG textures using box/per-face UV, applies cube rotations and hierarchical bone animation transforms at a requested timestamp. CPU-only; not pixel-identical to Blockbench or Minecraft. |
| Quality gates | ✅ | Bounds, proportions, thickness warnings, bone and cube limits, rig depth; `fail_on_warnings` opt-in |
| `app_*` desktop bridge | ⚠️ experimental | Optional Blockbench desktop plugin publishes read-only snapshots to filesystem. No network, no app mutation; actual Blockbench 5 testing pending |
| Full GeckoLib plugin compatibility | ⚠️ | **Not verified with Blockbench/GeckoLib runtime** |

These exporters implement a consciously restricted subset. Unsupported features should cause validation failure rather than silently disappear. `.bbmodel` is an evolving internal Blockbench format; inspect and re-save generated projects in Blockbench once before relying on them in a production mod.

## Security defaults

- **Zero runtime NPM dependencies**. Node.js 20+ required. No `npm install` required to run or test.
- **stdio only**: no HTTP, WebSocket, network client, process spawning, `eval` or arbitrary JS execution. Optional filesystem-based live bridge is disabled unless `--enable-live` is explicitly supplied.
- **Read-only by default**. Changes to `.bbmodel` require explicit `--allow-write`.
- Workspace root must be an existing absolute directory. Flat basenames only (no subdirectories, traversal or arbitrary paths).
- File size limit 5 MiB, JSON complexity limits, no symlinks/hardlinks for reading, safe new-file creation.
- Atomic revisions (SHA-256) and cooperative locks for edits; exports refuse overwrite unless `overwrite:true` with `--allow-write`.
- `geckolib_export_*` can compile in read-only mode; writing a file through `output_file` requires `--allow-write`.
- Don't auto-approve editing/writing actions from untrusted agents. Prompts and model files are not authorization mechanisms.

## Installation — Windows (PowerShell)

1. Extract this ZIP into `C:\Tools\blockbench-mcp-safe` (or your chosen location).
2. Install Node.js >=20 separately from a trusted distributor, and check `node --version`.
3. `New-Item -ItemType Directory -Force C:\BlockbenchModels`.
4. From the extracted project directory, run `npm test` and `npm run check`. These **do not download packages**.
5. Configure your MCP client as below. This tool is independent of the original GitHub repo.

```json
{
  "mcpServers": {
    "blockbench-geckolib-safe": {
      "command": "node",
      "args": [
        "C:/Tools/blockbench-mcp-safe/src/server.mjs",
        "--root", "C:/BlockbenchModels",
        "--allow-write"
      ]
    }
  }
}
```

Remove `--allow-write` for strict read-only mode. Client approvals are a separate security layer; prefer explicit approval for every write operation.

```powershell
# Claude Code example
claude mcp add blockbench-geckolib-safe -- node C:/Tools/blockbench-mcp-safe/src/server.mjs --root C:/BlockbenchModels --allow-write

# Codex example
codex mcp add blockbench-geckolib-safe -- node C:/Tools/blockbench-mcp-safe/src/server.mjs --root C:/BlockbenchModels --allow-write
```

## Tools (22)

| Tool | Action |
|---|---|
| `bbmodel_sample_pose` | Sample GeckoLib clip at time (seconds) to inspect numeric bone channels |
| `bbmodel_quality_gates` | Configurable bounds, proportions and rig quality validation |
| `bbmodel_render` | CPU contact sheet PNG, embedded as MCP image; optional atomic PNG save |
| `app_status` | Live bridge opt-in: current project information, read-only |
| `app_read_scene` | Live bridge opt-in: bones/cubes snapshot, read-only |
| `app_capture_screenshot` | Live bridge opt-in: best-effort viewport PNG, read-only |
| `bbmodel_list_files` | List safe `.bbmodel` basenames in workspace |
| `bbmodel_info` | Metadata + SHA-256 revision |
| `bbmodel_read_scene` | Inspect scene bones/outliner/cubes (max 250 elements) |
| `bbmodel_validate` | Generic structural validation |
| `bbmodel_create` | Create Generic/free model (write) |
| `bbmodel_edit` | Cubes, groups, bone pivots, mesh add/remove in Generic, per-face UV and rotations; requires revision (write) |
| `bbmodel_duplicate` | New `.bbmodel` copy (write) |
| `bbmodel_geckolib_create` | Create `geckolib_model` (write) |
| `bbmodel_geckolib_upsert_animation` | Add/replace clip with numeric keyframes with allowlisted linear, Catmull-Rom and GeckoLib easing (write) |
| `bbmodel_geckolib_remove_animation` | Remove entire animation (write) |
| `bbmodel_geckolib_remove_track` | Remove named bone/channel track (write) |
| `bbmodel_geckolib_set_texture` | Embed validated PNG in `.bbmodel` and link texture UUID on all cube faces (write) |
| `bbmodel_geckolib_read_scene` | Compact hierarchical rig, cube coordinates and animation track counts |
| `bbmodel_geckolib_validate` | GeckoLib subset validator; `require_idle_walk:true` and optional `required_animations` |
| `bbmodel_geckolib_export_geometry` | Return `.geo.json` or write with `overwrite` default false (opt-in write) |
| `bbmodel_geckolib_export_animations` | Return `.animation.json` or write with `overwrite` default false (opt-in write) |

### Workflow for an AI coding agent — atomic steps

1. **Create project:** call `bbmodel_geckolib_create` with `{"file":"mob.bbmodel","identifier":"mob","modid":"examplemod","model_type":"Entity","texture_width":64,"texture_height":64}`.
2. **Create root bone:** call `bbmodel_edit`, providing `expected_revision` from step 1 and `operations:[{"op":"add_group","name":"root","origin":[0,0,0]}]`. Keep returned group UUID and revision.
3. **Create nested bones:** call `bbmodel_edit` again with `{"op":"add_group","name":"body","origin":[0,12,0],"parent_group_uuid":"<ROOT_UUID>"}`; create head, arms and legs likewise. `origin` is the Blockbench editor pivot; on export bone X pivots flip as needed for Bedrock.
4. **Add cubes:** `{"op":"add_cube","name":"chest","group_uuid":"<BODY_UUID>","from":[-4,12,-2],"to":[4,22,2],"uv_offset":[0,0]}`. Every GeckoLib cube requires a bone.
5. **Optional texture:** Put a 64x64 PNG in `--root`, then call `bbmodel_geckolib_set_texture` with `{file:"mob.bbmodel",expected_revision:"<LATEST_REVISION>",png_file:"skin.png"}`. The PNG is embedded into the model and cube faces reference its UUID. A checker PNG is provided as an example, not a final mob skin.
6. **Add animation:** call `bbmodel_geckolib_upsert_animation` with e.g. `name:"animation.mob.walk",length:1,loop:"loop",channels:[{"bone":"left_leg","channel":"rotation","keyframes":[{"time":0,"value":[0,0,0]},{"time":0.5,"value":[30,0,0]},{"time":1,"value":[0,0,0]}]}]`. Repeat for `animation.mob.idle`.
7. **Validate:** call `bbmodel_geckolib_validate` with `require_idle_walk:true` (or exact `required_animations:["animation.mob.idle","animation.mob.walk"]`). Fix errors; investigate warnings.
8. **Export:** call `bbmodel_geckolib_export_geometry` with `output_file:"mob.geo.json"`, then `bbmodel_geckolib_export_animations` with `output_file:"mob.animation.json"`. Existing exports are **never silently overwritten**: an iterative export can pass `overwrite:true` if `--allow-write` is enabled. The tool returns `{path, overwritten, sha256}`.
9. **Verify manually:** open `mob.bbmodel` in Blockbench 5 with the **GeckoLib Models & Animations** plugin installed; inspect hierarchy, playback, UV atlas and native export output. Place exported assets under your mod's resource directories and supply a separately exported PNG; GeckoLib `geo.json` does not contain the embedded `.bbmodel` PNG.

Important: each modifying call returns a **new revision**. Always pass the latest SHA-256 hash to the next edit. UUID values above are placeholders, not literals.

## Example GeckoLib mob included

In `examples/`:

- `gecko_test_mob.bbmodel` — 7 bones (`root`, `body`, `head`, both arms, both legs), 6 cubes and idle/walk clips.
- `gecko_test_mob.geo.json` — exported geometry.
- `gecko_test_mob.animation.json` — exported animations.

A `contact_sheet_cpu.png` diagnostic preview is also included. The original example is untextured. New v0.5.0 previews `textured_rest.png`, `textured_walk_025.png`, `textured_walk_050.png`, and `flat_rest.png` demonstrate actual PNG sampling and sampled bone animation. Additional demo files `gecko_test_mob_textured.bbmodel`, `checker_64.png`, `gecko_test_mob_textured.geo.json` and `.animation.json` show embedded PNG references using this server. They are not production art. See `examples/README.md`.

## Verify locally

```powershell
npm run check
npm test
npm run sums
```

Tests use Node's built-in `node:test` including mocked desktop-bridge integration: protocol stdio, read/write permissions, workspace traversal restrictions, file safety, concurrent edits, geometry/animation correctness and negative validation cases. The `npm run sums` command deterministically regenerates `SHA256SUMS.txt`. See `SECURITY.md` for residual risks.

## Compatibilidad pendiente (Blockbench 5.x)

`test/fixture-compat.test.mjs` contains a compatibility test that runs only if an **authentic** `test/fixtures/blockbench5_geckolib_min.bbmodel` has been exported manually from Blockbench 5.x with GeckoLib Animation Utils. Until then it is **skipped**. See `test/fixtures/README.md` for the steps. Internal automated tests do **not** prove native exporter byte-equivalence, in-game correctness or live Blockbench compatibility.

## GeckoLib animation track controls

Use `bbmodel_geckolib_upsert_animation` with `replace:true` and `replace_tracks:false` to preserve existing tracks not included in the incoming `channels[]`. With `replace_tracks:true` (default), the whole clip's tracks are replaced. Use `bbmodel_geckolib_remove_track {file,expected_revision,name,bone,channel}` or `bbmodel_geckolib_remove_animation {file,expected_revision,name}` for deliberate deletions. Always use the newest `revision` returned by any write before the next edit. `interpolation` is allowed per keyframe (default `linear`), e.g. `catmullrom` maps to `lerp_mode` and `easeInOutSine` maps to `easing` in the animation JSON.

The X-axis mirror convention is unchanged from v0.2.0; do not pre-mirror user coordinates. The `mirror:true` cube option is distinct from the global X-axis exporter coordinate transformation and emits `"mirror":true` per cube.

## Technical references

- Blockbench internal project format: https://blockbench.net/wiki/docs/bbmodel/
- GeckoLib model exports: https://wiki.geckolib.com/docs/geckolib5/making-models/exporting-the-files/
- GeckoLib animation examples: https://github.com/JDKDigital/productive-bees/blob/dev-1.21.0/src/main/resources/assets/productivebees/animations/entity/bee.animation.json
- Blockbench format conversion research: https://github.com/Kaioga5/BBModel-Unpack/blob/main/docs/FORMAT-NOTES.md

## License

BlockMinion Source-Available License (see the repository `LICENSE`; earlier versions were MIT). Independently authored implementation. No source from the original GPL-3.0 project is bundled. Trademarks remain with their respective owners. This is not an official GeckoLib or Blockbench product.

## v0.5.0 usage: textured, pose-aware visual feedback and desktop bridge

### CPU rendering / contact sheets

Call `bbmodel_render` with:

```json
{"file":"mob.bbmodel","views":["front","right","back","iso"],"size":160}
```

`bbmodel_render` samples the first embedded PNG texture (if present), maps UVs per face or using Blockbench box UV nets, and returns a `type:"image", mimeType:"image/png"` plus JSON metadata. Without texture, or with `textures:false`, it renders flat shading. UV rotation at multiples of 90° and mirrored box UV are supported. Supported views: `front`, `back`, `left`, `right`, `top`, `iso`.

For a walk pose at **0.25 seconds**, call:

```json
{"file":"mob.bbmodel","animation":"animation.gecko_test_mob.walk","time":0.25,"wrap":true,"textures":true,"views":["front","left","back","iso"],"size":160}
```

You can omit `animation` and `time` for rest pose. `time` without an `animation` is rejected. Animation uses the same numeric interpolation implementation as `bbmodel_sample_pose`, including `catmullrom`, easing presets and loop wrapping. Bone/parent transforms and element Euler rotations are composed hierarchically in Blockbench 5 coordinates.

Set `output_file:"mob-preview.png"` and optionally `overwrite:true` to save a PNG atomically in `--root` (requires `--allow-write`). If the PNG would exceed the safe MCP image response budget, the server requires `output_file`; an oversized stored image is returned as metadata with `image_omitted:true`. The renderer is entirely CPU-driven with a 450-triangle budget, `size` from 64 to 320 pixels per view, and maximum six views. It never loads texture filenames or URLs from within a model: **only embedded PNG data is decoded**.

**Compatibility scope:** This is a software **diagnostic preview**, not Blockbench's WebGL renderer. It does not apply materials, lighting/shadows, blend shapes, Molang, animation controllers, exact Euler parity, GPU shaders or project-wide texture stacks. Image pixels and rig playback still need native Blockbench + GeckoLib verification. PNG decoding supports non-interlaced 8-bit RGB/RGBA/gray-alpha or 1/2/4/8-bit grayscale/indexed images; 16-bit textures are rejected with an actionable error. Transparent pixels are supported with basic depth blending; exact transparent triangle ordering is not guaranteed.

**Texture validation:** `bbmodel_validate` no longer emits the obsolete warning that textures are not rendered. A single embedded PNG can be decoded by `bbmodel_render`; validation itself checks only the source form, not the PNG image bytes. External or multiple texture sources still generate accurate preview-limit warnings.

### Animation sampling and quality gates

```json
{"file":"mob.bbmodel","animation":"animation.mob.walk","time":0.25,"wrap":true}
```

`bbmodel_sample_pose` and `bbmodel_render` both accept the `animation` field (not `name`) for the clip name. Existing agents configured for v0.5.0 need to update their `bbmodel_sample_pose` arguments; the old `name` field is rejected with a list of valid fields.

`bbmodel_sample_pose` returns **local** channels `position`, `rotation` (degrees) and `scale`, per bone, with rest pivot and rest rotation reported separately. Keyframes are interpolated; looping clips wrap by length. This numerical sampler does **not** produce global transform matrices or guarantee exact playback matches in GeckoLib runtime.

`bbmodel_quality_gates` example:

```json
{"file":"mob.bbmodel","max_span":48,"max_axis_ratio":12,"max_cubes":128,"max_bones":64,"min_thickness":0.1,"max_bone_depth":12,"fail_on_warnings":true}
```

Bounds/proportion/bone/cube limits are errors; thin geometry and empty-bone findings are warnings, optionally treated as failures. These are **quality heuristics**, not hard Minecraft gameplay limits.

### Mesh authoring in Generic .bbmodel

Create a Generic model with `bbmodel_create`, then invoke `bbmodel_edit` with the latest revision:

```json
{
  "file":"generic.bbmodel", "expected_revision":"<SHA256>",
  "operations":[{"op":"add_mesh","name":"Triangle","vertices":{"a":[0,0,0],"b":[4,0,0],"c":[0,4,0]},"faces":{"surface":{"vertices":["a","b","c"],"uv":{"a":[0,0],"b":[4,0],"c":[0,4]}}}}]
}
```

Mesh faces support triangles or quads, with per-vertex UV. `remove_mesh` needs the UUID. This is **.bbmodel authoring / CPU preview only**. GeckoLib exporter deliberately does not emit `poly_mesh`: it is deprecated and in-game compatibility is unverified. Use cube-based geometry for mobs until a tested mesh export path exists.

### Per-face UV for GeckoLib cubes

Create/update a cube using `uv_faces` instead of `uv_offset`, e.g.:

```json
{"op":"update_cube","uuid":"<CUBE_UUID>","uv_faces":{"north":{"uv":[0,0,8,8]},"up":{"uv":[8,0,16,8],"rotation":90},"down":{"uv":[0,8,8,16],"enabled":false}}}
```

Each face accepts `uv: [u1,v1,u2,v2]`, optional `rotation:0|90|180|270`, and `enabled:false` to omit it. Partial `uv_faces` updates preserve the other faces; changing `uv_offset` switches back to box-UV. `geo.json` uses Bedrock `uv_size` and `uv_rotation` for rotations; rotations require geometry format 1.21.0. **Verify actual GeckoLib and Minecraft support with your target game version.**

### Optional read-only live Blockbench bridge

1. Launch the server using `--root C:/BlockbenchModels --enable-live` (you do **not** need `--allow-write` for live reading).
2. In the **Blockbench desktop 5.x app**, manually load `plugin/blockbench_mcp_safe_bridge.js` using Blockbench's plugin import UI. Review the code first.
3. Under **Tools → Connect Read-Only MCP Safe Bridge**, paste the *same* absolute workspace directory when requested. Click the action again to disconnect.
4. Use `app_status`, `app_read_scene` or `app_capture_screenshot`. Snapshots are updated about every 2 seconds. `app_capture_screenshot` is best-effort and may fail on certain GPU drivers or large canvases; `app_status`/`app_read_scene` can still work.

**Security:** no HTTP listener, no command dispatcher, no arbitrary app actions, no model mutation. The plugin writes scene/status PNG snapshots into `--root/.bbms-live` and MCP reads from that fixed path. Snapshot content may include private model information. Use a private workspace and disconnect the plugin when not needed. The bridge was integration-tested with a **mock Blockbench environment**, not yet verified in the real desktop app.

### Known compatibility limits

A genuine Blockbench 5.x + GeckoLib saved fixture, in-game validation and physical desktop-plugin integration remain outstanding. GPU-accurate shading, exact Blockbench/GeckoLib animation playback parity, world-space matrix outputs from `bbmodel_sample_pose`, or writable `app_*` controls have **not** been implemented. `bbmodel_render` is intentionally CPU-driven rather than depending on a GPU/renderer dependency.
