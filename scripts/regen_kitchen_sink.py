"""Regenerate the craftctl-made part of examples/kitchen_sink (run with CRAFTCTL_HOME set to a scratch dir), then re-apply the hand-written classes."""
import subprocess
cmds = [
 'craftctl new --name "Kitchen Sink" --id kitchen_sink --package com.example.kitchensink --idea "items: sky crystal; blocks: crystal ore; tab: Kitchen Sink"',
 'craftctl add-feature kitchen_sink --kind block --label "Crystal Station" --id crystal_station --tool pickaxe --mining-level stone',
 'craftctl add-feature kitchen_sink --kind block --label "Crystal Bricks" --id crystal_bricks --tool pickaxe',
 'craftctl set-variants kitchen_sink --block crystal_bricks --variants stairs slab fence wall',
 'craftctl add-enchantment kitchen_sink --id crystal_edge --label "Crystal Edge" --kind damage',
 'craftctl add-ore kitchen_sink --block crystal_ore --vein-size 8 --veins-per-chunk 6 --min-y -64 --max-y 32',
 'craftctl add-sound kitchen_sink --id crystal_chime --label "Crystal chimes" --category block',
 'craftctl add-mob kitchen_sink --id sky_critter --label "Sky Critter" --spawn overworld --spawn-weight 8 --spawn-group 2 4',
 'craftctl plan kitchen_sink', 'craftctl approve-spec kitchen_sink', 'craftctl generate kitchen_sink']
for c in cmds: subprocess.run(c, shell=True, check=True, capture_output=True)
print("generated; now copy src/ over examples/kitchen_sink and re-apply the hand-written classes (see git history)")
