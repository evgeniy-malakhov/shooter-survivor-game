# Neon Outbreak

Top-down shooter prototype in Python with a shared simulation core for single-player and online modes.

## Features

- Single-player and online client modes from one Pygame menu.
- Separate asynchronous TCP server in `server/`.
- Shared game rules in `shared/` so local and online gameplay stay consistent.
- Mouse aiming, left-click shooting, reload, pickup, weapon slots `1` through `0`.
- Visual HUD with health, armor, ammo, selected weapon, minimap and inventory overlay.
- Lootable weapons, ammo, medkits and armor.
- Zombie bot archetypes: fast runners, balanced walkers and armored brutes.
- Leaper zombies sprint faster during chase, weave side to side, spit poison and leave temporary toxic pools when they miss.
- AI perception with field-of-view cones, blind zones, hearing sensitivity, noise investigation, chase, search and patrol modes.
- Large 9600x6600 map with buildings, walls, doors, interiors, props and stairs.
- Multi-floor interiors with basements, work benches, repair tables and floor-specific visibility.
- Basement tunnel network connecting buildings. Tunnels are dark; flashlight modules reveal loot and navigation.
- Grid backpack with body armor slots, drag/drop, item dropping, consumables, resources, crafting and armor repair.
- Quick slots can hold weapons, grenades or mines; weapons can be reordered by dragging them between slots.
- Weapon customization supports utility and magazine module slots. Laser sights tighten aim, flashlights light tunnels, and extended magazines increase capacity.
- Weapons and equipped armor have durability. Drag a repair kit onto a damaged item to repair it.
- Online scoreboard with per-player kills by zombie type and online respawn.
- Main-menu visual settings with bot density and difficulty presets for new single-player runs.
- Difficulty balance files in `configs/difficulty/` control zombie stats, weapon damage, equipment wear, spawn pacing and loot volume.
- JSON localization files in `locales/` for English and Russian UI text.
- Optimized TCP protocol based on asyncio Protocol, length-prefixed frames, optional msgpack encoding, per-client output queues, logical reliable/unreliable channels, interest filtering and compact delta snapshots.
- Online netcode supports input acknowledgement, client-side prediction, reconciliation and interpolation buffering for smoother remote entities.
- Gameplay events are streamed separately from state snapshots for effects such as shots, hits, deaths, explosions, pickups and transactional command results.

## Install

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If your system uses `python` instead of `py`, replace `py` with `python`.

## Run Single Player

```powershell
python -m client.main
```

Choose `Single Player` in the menu.

Open `Visual Settings` from the main menu before starting to choose bot density and difficulty. Difficulty presets are loaded from JSON files in `configs/difficulty/`.

## Run Online

Start the server in a separate terminal:

```powershell
python -m server.main --host 127.0.0.1 --port 8765 --difficulty medium
```

For profiling network queues and snapshot timings:

```powershell
python -m server.main --host 127.0.0.1 --port 8765 --difficulty medium --profile
```

Start the client:

```powershell
python -m client.main
```

Choose `Online`, wait for ping values in the server list, select a server and press `Connect`.

Servers are configured in [servers.json](servers.json). Add more entries like this:

```json
[
  { "name": "Local Dev", "host": "127.0.0.1", "port": 8765 }
]
```

Server difficulty can be `easy`, `medium`, `hard` or `insane`. In online mode the server owns the world balance.

Server networking is configured in `configs/server.json`. The current online protocol uses optimized TCP frames with compact snapshot schema `compact-v1`. UDP is exposed as a reserved launch option for future protocol work, but the playable server currently runs on TCP.

## Controls

- `Mouse move`: aim.
- `Left mouse`: shoot.
- `Right mouse`: move toward cursor.
- `WASD`: movement.
- `Shift`: sprint. Sprinting is louder and attracts zombies from farther away.
- `Ctrl`: sneak. Sneaking is slower and silent.
- `R`: reload.
- `E`: pick up loot nearby.
- `F`: open/close nearby doors or use stairs inside buildings.
- `Q`: toggle the active weapon utility module, such as laser or flashlight.
- `G`: throw a grenade from the backpack. Impact grenades explode on contact, standard grenades detonate after 2 seconds, and heavy grenades detonate after 3 seconds.
- `1`-`9`, `0`: select weapon or quick-slot grenade/mine.
- `Left mouse` with a selected mine: place it on the field. It arms after you leave its trigger radius.
- `B`: backpack.
- `C`: crafting menu near a basement work bench.
- `O` or `Esc` in game: visual settings. Online mode keeps running; single-player pauses while overlays are open.
- `I`: legacy inventory/backpack toggle.
- `M`: minimap size.
- `Tab`: hold online/local scoreboard.
- `Space`: respawn after death. Respawn tries to place you in a safe interior or far from active zombies.
- `Esc`: back to menu or close inventory.

## AI Notes

Zombies no longer know the player position for free. Each bot has:

- sight range, field-of-view angle and a blind zone behind it;
- hearing range and sensitivity to player noise;
- patrol, investigate, chase and search states;
- a five-second search window at the last known position.

Walls and closed doors block vision and movement. Open doors create valid passages, so a zombie can enter a building and continue searching if it saw the player. Zombies ignore noise made by players inside buildings, so closing a door and staying out of sight becomes a real stealth option.

## Backpack, Crafting And Repair

Loot now goes into the backpack when possible. Right-click food or medical items to start gradual healing; taking damage cancels the healing process. Drag armor pieces into body slots to equip them, drag items to other cells to reorganize, or drop them into the drop zone to spawn them near the player for everyone in online mode.

Work benches are in basements and open the crafting menu with `C`. Repair tables are usually on the first floor; repair equipped armor from the backpack screen if you have a repair kit.

Light armor can be found in the world. Medium and heavy armor pieces are crafted for each body slot. Drag a repair kit directly onto damaged weapons or equipment to consume the kit and restore durability.

Open the backpack and press `Customize Weapon` to install modules. Utility slots accept a laser sight or flashlight; magazine slots accept an extended magazine. While weapon customization is open, close it before switching to crafting or closing the backpack.

Explosive balance is configured in `configs/explosives.json`. Starting backpack contents are configured in `configs/backpack.json`, and item stack sizes are configured in `configs/item_stacks.json`.

## Localization

UI text is loaded from JSON files in `locales/`. The game includes `en.json` and `ru.json`; switch language from `Visual Settings`.

## Project Layout

```text
client/   Pygame application, UI, rendering and online network client.
server/   Asyncio TCP game server and bot loop.
shared/   Protocol, dataclasses and deterministic game simulation.
```

The server is authoritative for online mode. The client sends sequenced movement input, never authoritative positions. Transactional actions such as pickup, interact, inventory drag/drop, craft, repair, equip, reload, respawn and utility toggles use reliable ordered `command` messages with `command_result` acknowledgements. Snapshots include `ack_input_seq`, `server_time` and `snapshot_interval`; the client drops acknowledged inputs, predicts the local player and interpolates other entities with a short buffer. Each client receives only nearby high-frequency entities through interest management while scoreboard-safe player metadata remains available.
