"""CI: give the generated ci_mod a scaled mob and a 3D sword the way the controller would, so Gradle compiles the code
those features add (Attributes.SCALE in an entity, the 3D item renderer classes, the client entrypoint)."""
import json
import sys
from pathlib import Path

from mod_orchestra.model3d import install_item3d, request_item3d
from mod_orchestra.models import set_mob_scale
from mod_orchestra.skin import encode_png
from mod_orchestra.state import Store

store = Store(None)
pid, item = "ci_mod", "ci_sword"
print("scale:", set_mob_scale(store, pid, "ci_stalker", 1.5)["how"])
task = request_item3d(store, pid, item, "CI")["task"]
ws = Path(store.project(pid)["root"]); d = ws / "models/items3d"; d.mkdir(parents=True, exist_ok=True)
px = bytes(c for y in range(16) for x in range(16) for c in ((90, 90, 110, 255) if (x + y) % 3 else (200, 200, 220, 255)))
png = encode_png(16, 16, px)
geo = {"format_version": "1.12.0", "minecraft:geometry": [{"description": {"identifier": f"geometry.{item}", "texture_width": 16, "texture_height": 16},
       "bones": [{"name": "blade", "pivot": [0, 0, 0], "cubes": [{"origin": [-1, 2, -0.5], "size": [2, 13, 1], "uv": [0, 0]}]},
                 {"name": "guard", "parent": "blade", "pivot": [0, 2, 0], "cubes": [{"origin": [-3, 2, -1], "size": [6, 1, 2], "uv": [0, 14]}]}]}]}
anim = {"format_version": "1.8.0", "animations": {f"animation.{item}.idle": {"loop": True, "animation_length": 2,
        "bones": {"blade": {"rotation": {"0.0": {"vector": [0, 0, 0]}, "1.0": {"vector": [0, 10, 0]}, "2.0": {"vector": [0, 0, 0]}}}}}}}
(d / f"{item}.geo.json").write_text(json.dumps(geo)); (d / f"{item}.animation.json").write_text(json.dumps(anim))
(d / f"{item}.png").write_bytes(png); (d / f"{item}_render.png").write_bytes(png); (d / f"{item}.bbmodel").write_text("{}")
out = install_item3d(store, pid, task, item, run_id="ci-item3d", actor="ci")
print("item3d installed:", out["installed"], "animated:", out["animated"], "coder:", out["wire_task"])
if out["wire_task"]:
    sys.exit("the controller could not wire a freshly generated project by itself")
