# kitchen_sink — compiled reference for the knowledge skills

Generated with `craftctl` (items, an ore with tool tags, a sound event, a naturally spawning mob) and then extended by hand
with one class per pattern the coder's knowledge skills teach. CI builds this project on every push: if a skill's code
stops compiling against the pinned Fabric/Minecraft versions, the build fails and the skill is wrong.

| Skill | Class |
|---|---|
| events | `EventsExample` |
| commands | `CommandsExample` |
| loot-and-trades | `LootAndTradesExample` |
| polish (config) | `ModConfig` |
| client-ui | `client/ClientUiExample`, `OpenPayload` (C2S), `ManaSyncPayload` (S2C with data), `client/ClientState` |
| data | `DataExample` (player attachment, item component), `ModSaveData` (world data) |
| gui | `BackpackItem` (vanilla chest menu), `StationMenu` + `client/StationScreen` |

Press **B** in-game to open the example menu; `/sky give 3`; the HUD shows an example bar; the Backpack is in the Kitchen Sink tab.
