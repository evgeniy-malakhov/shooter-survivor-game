# Game Configuration Guide

All files in this folder are UTF-8 JSON, except this documentation file. Restart the game or server after changing balance configs, because they are loaded when Python modules are imported.

## Core Files

- `weapons.json` configures hand weapons.
- `zombies.json` configures enemy archetypes.
- `armors.json` configures base armor tiers.
- `rarities.json` configures item rarity colors and bonuses.
- `explosives.json` configures thrown grenades and placed mines.
- `weapon_modules.json` configures laser, flashlight and magazine modules.
- `audio.json` configures menu music, action sound folders, weapon sound mapping and spatial shot falloff.
- `crafting.json` configures crafted item rarity chances.
- `backpack.json` configures the starting backpack.
- `item_stacks.json` configures stack sizes for backpack items.
- `icon_mapping.json` maps game ids to PNG filenames in `images/`.
- `death_effects.json` configures client-side corpse, blood spread and fade timings.
- `server.json` configures server networking, interest management, output queues and profiling thresholds.
- `difficulty/*.json` configures world difficulty presets.

## Items

Item definitions live in `shared/items.py`; stack limits live in `item_stacks.json`; display names live in `locales/en.json` and `locales/ru.json`; icons are loaded from `images/` by item key or by `icon_mapping.json`.

Current items:

- Food: `apple`, `canned_food`, `energy_bar`.
- Medical: `bandage`, `medicine`.
- Resources: `scrap`, `cloth`, `duct_tape`, `circuit`, `gunpowder`.
- Ammo/tool: `ammo_pack`, `repair_kit`.
- Grenades: `contact_grenade`, `grenade`, `heavy_grenade`.
- Mines: `mine_light`, `mine_standard`, `mine_heavy`.
- Weapon modules: `laser_module`, `flashlight_module`, `extended_mag`.
- Armor pieces: `light_head`, `light_torso`, `light_arms`, `light_legs`, `medium_head`, `medium_torso`, `medium_arms`, `medium_legs`, `heavy_head`, `heavy_torso`, `heavy_arms`, `heavy_legs`.

To add a new item:

1. Add its `ItemSpec` in `shared/items.py`.
2. Add a stack limit in `item_stacks.json`.
3. Add localized names in `locales/en.json` and `locales/ru.json` using `item.<key>`.
4. Add it to `HOUSE_LOOT` or `WORLD_LOOT` in `shared/items.py` if it should spawn.
5. Add a recipe in `RECIPES` if it should be craftable, and localize `recipe.<key>`.
6. Add a PNG to `images/<key>.png`, or add an entry to `icon_mapping.json` if another filename should be reused.

## Icon Mapping

`icon_mapping.json` is a simple object where each key is the game id and each value is the PNG filename without extension. The client first loads every `images/*.png` by filename, then applies this mapping as aliases.

Examples:

- `grenade` maps to `granade` because the current PNG filename is `granade.png`.
- `gunpowder` maps to `gun_powder`.
- `duct_tape` maps to `dust_type`.
- `light_head` maps to `light_helmet`.
- Rarity badges use `common`, `uncommon`, `rare` and `legendary`.

When adding a new item, prefer naming the PNG exactly like the item key. Use `icon_mapping.json` only for legacy filenames, shared icons, or deliberately reused visuals.

## Crafting

`crafting.json` controls the rarity roll for items created at a work bench. Every crafted item receives a rarity, including consumables, tools, explosives, modules and armor.

Fields:

- `rarity_weights`: default craft weights for `common`, `uncommon`, `rare` and `legendary`.
- `kind_overrides`: optional weights by resulting item kind, such as `armor`, `weapon_module`, `grenade` or `mine`.
- `recipe_overrides`: optional weights for one exact recipe key. This has the highest priority.

Example:

```json
{
  "recipe_overrides": {
    "heavy_torso": {
      "common": 40,
      "uncommon": 34,
      "rare": 20,
      "legendary": 6
    }
  }
}
```

The work bench UI shows these configured odds directly on recipe cards with rarity icons.

## Weapons

`weapons.json` entries are keyed by weapon id. Every weapon supports:

- `title`: fallback display name.
- `slot`: default quick slot, usually `1` to `0`.
- `damage`: base damage before difficulty and rarity multipliers.
- `magazine_size`: base magazine capacity.
- `fire_rate`: shots per second.
- `reload_time`: seconds to reload.
- `projectile_speed`: projectile velocity.
- `spread`: base inaccuracy in radians.
- `pellets`: projectile count per shot, useful for shotguns.

Current weapons:

- `pistol`: accurate starter weapon.
- `smg`: fast low-damage automatic weapon.
- `shotgun`: short-range multi-pellet burst weapon.
- `rifle`: higher-damage accurate weapon.

Weapon rarity is stored on each dropped or owned weapon. Rarity multiplies final weapon damage and reduces durability wear.

## Armors

`armors.json` entries are base armor tiers:

- `none`: no armor.
- `light`: findable light armor tier.
- `medium`: craft-focused medium tier.
- `tactical`: legacy tactical tier used by older loot paths.
- `heavy`: high-protection armor tier.

Fields:

- `title`: fallback display name.
- `mitigation`: damage reduction ratio before rarity.
- `armor_points`: armor bar capacity before rarity.

Armor items store their own rarity. Rarity increases armor points, mitigation and durability resistance.

## Rarities

`rarities.json` controls rarity balance for weapons and armor:

- `common`: gray, baseline stats.
- `uncommon`: blue, modest stat and durability bonus.
- `rare`: purple, strong stat and durability bonus.
- `legendary`: gold, highest bonus and lowest spawn chance.

Fields:

- `title`: fallback title.
- `color`: `[red, green, blue]` used on map, backpack, quickbar and drag preview.
- `loot_weight`: weighted spawn chance for weapon and armor loot.
- `weapon_damage_multiplier`: multiplies weapon damage.
- `weapon_durability_multiplier`: divides weapon wear.
- `armor_points_multiplier`: multiplies armor bar capacity.
- `armor_mitigation_multiplier`: multiplies armor damage reduction.
- `armor_durability_multiplier`: divides armor wear.

Higher rarity weapons and armor are shown with their rarity color on the map and in inventory UI.

## Death effects

`death_effects.json` controls visual-only death effects. These effects are not physics entities: bullets, players and zombies ignore corpses and blood.

- `corpse_seconds`: how long a zombie corpse or fresh player death marker remains visible.
- `corpse_fade_seconds`: how long the final fade-out lasts.
- `blood_seconds`: how long the blood pool remains visible.
- `blood_spread_seconds`: how long the blood pool keeps expanding.
- `blood_fade_seconds`: how long the final blood fade-out lasts.
- `blood_start_radius` / `blood_end_radius`: world-space radius range for the spreading blood pool.
- `blood_alpha`: maximum blood opacity.
- `corpse_dark_alpha`: darkness applied over dead zombie bodies.
- `player_cross_size` / `player_cross_width`: black cross size and stroke width for dead players.
- `max_effects`: maximum number of active local death effects kept by the client.

## Audio

`audio.json` keeps sound asset routing out of code:

- `menu_music`: relative or absolute path to the menu music MP3.
- `actions_dir`: folder containing short action sounds such as shots, reloads and empty weapon clicks.
- `weapon_sounds`: per-weapon mapping for `shot`, `reload` and `empty` sound keys. Sound keys match filenames in `actions_dir` without extension.
- `shot_hearing_distance`: maximum world distance where remote shots are audible.
- `shot_full_volume_distance`: distance where shots still play at full volume before falloff begins.
- `different_floor_volume_multiplier`: volume multiplier for sounds on another building floor.
- `min_spatial_volume`: cutoff below which very quiet distant sounds are skipped.

The client has three audio sliders: master volume affects every sound, music affects menu music, and effects affects shots, reloads and empty weapon clicks.

## Explosives

`explosives.json` has two sections: `grenades` and `mines`.

Grenade fields:

- `title`: fallback display name.
- `timer`: detonation timer in seconds.
- `contact`: if true, detonates on wall or actor contact.
- `throw_distance`: initial throw velocity/distance feel.
- `blast_radius`: damage radius.
- `zombie_damage`, `zombie_damage_bonus`: scaled damage to enemies.
- `player_damage`, `player_damage_bonus`: scaled damage to players.

Current hand-carried grenades:

- `contact_grenade`: explodes on contact and throws farther.
- `grenade`: standard 2-second fragmentation grenade.
- `heavy_grenade`: 3-second heavy grenade with double standard radius and damage.

Mine fields:

- `trigger_radius`: radius that arms/triggers the mine.
- `blast_radius`: explosion damage radius.
- Damage fields match grenade damage fields.

Current mines:

- `mine_light`: smaller trigger and blast radius, easier to carry.
- `mine_standard`: balanced field mine.
- `mine_heavy`: larger radius and damage, rarer and heavier in stack limits.

Mines are selected in a quick slot and placed with left mouse. A placed mine becomes active only after the owner leaves its trigger radius. Once active, enemies or players entering the trigger radius detonate it.

## Zombies

`zombies.json` entries are keyed by enemy type:

- `walker`: standard balanced enemy.
- `runner`: fast, low-health enemy.
- `brute`: slow armored enemy.
- `leaper`: chase-specialist enemy with sidestep movement and poison spit.

Fields:

- `title`: fallback display name.
- `health`, `armor`, `speed`, `damage`, `radius`: combat stats.
- `color`: `[red, green, blue]` for rendering.
- `sight_range`: maximum vision range.
- `hearing_range`: base hearing range.
- `fov_degrees`: field of view cone.
- `sensitivity`: reaction multiplier for noise.
- `suspicion_time`: tuning value for detection behavior.

If you add a zombie key, also add localized scoreboard labels if you want it displayed separately.

## Starting Backpack

`backpack.json`:

- `slots`: backpack cell count.
- `starting_weapon.key`: weapon key from `weapons.json`.
- `starting_weapon.reserve_ammo`: reserve ammo.
- `starting_items`: list of `{ "key": "...", "amount": N }`.

Starting items are created as common rarity.

## Stack Sizes

`item_stacks.json` maps item keys to maximum stack amounts. Armor and modules usually stay at `1`. Explosives are intentionally lower than resources.

## Difficulty

`difficulty/*.json` controls the world-level multipliers:

- zombie count, health, armor, speed and damage;
- weapon and armor wear;
- global and per-weapon damage multipliers;
- loot spawn amount and spawn interval.

Difficulty is applied by the authoritative server in online mode.

## Server Networking

`server.json` controls the optimized online server. The default profile is aimed at smooth 1-10 player sessions with 50 players as the practical cap:

- `simulation.tick_rate`: authoritative simulation ticks per second. Higher values improve responsiveness but increase CPU cost.
- `simulation.snapshot_rate`: maximum snapshot send rate per client before adaptive throttling. The default keeps small 1-15 player sessions at 24 Hz while the client predicts local movement every rendered frame.
- `simulation.zombie_ai_decision_rate`: near-player zombie perception/decision rate in Hz. Movement and collisions still run every server tick; this only controls expensive sight/hearing decisions.
- `simulation.zombie_ai_far_decision_rate`: slower perception rate for zombies outside the active player radius.
- `simulation.zombie_ai_active_radius`: player distance that promotes a zombie to the near decision rate.
- `simulation.zombie_ai_far_radius`: maximum distance used when selecting players for zombie AI decisions before expensive line-of-sight checks.
- `simulation.zombie_ai_batch_size`: maximum zombie decision tasks scheduled per simulation tick. This staggers AI work instead of making every zombie think on the same frame.
- `simulation.zombie_ai_process_workers`: process workers used for zombie AI decisions. Use `0` to keep decisions in the simulation thread, or override at launch with `--zombie-workers`.
- `network.max_clients`: hard cap for simultaneously connected players. Resume tickets do not count as connected players, but they still keep players in the world until timeout.
- `network.listen_backlog`: TCP accept backlog for connection bursts during load tests or server-list joins.
- `network.interest_radius`: radius around each player for high-frequency entities such as zombies, loot, projectiles, grenades, mines and poison pools.
- `network.building_interest_radius`: larger radius used for building state so doors/interiors arrive before the player reaches them.
- `network.grid_cell_size`: spatial hash cell size used by interest management.
- `network.output_queue_packets`: maximum queued outbound packets per client. If a client falls behind, old snapshot packets are dropped and the next snapshot is forced full.
- `network.command_queue_limit`: maximum reliable commands waiting for one player inside the simulation runner.
- `network.snapshot_send_batch_size`: number of clients served by one delivery batch inside a snapshot round. The server time-slices batches across the round, so one large client list does not monopolize the event loop.
- `network.max_pending_snapshots_per_client`: maximum stale realtime snapshots kept per client. Keep this at `1` for realtime gameplay; old snapshots are not useful.
- `network.adaptive_snapshot_medium_clients` / `network.adaptive_snapshot_medium_rate`: when the online match reaches this player count, cap snapshot delivery to the configured medium rate. Defaults keep 16-32 players at 20 Hz.
- `network.adaptive_snapshot_high_clients` / `network.adaptive_snapshot_high_rate`: high-load snapshot cap for the 33-44 player range.
- `network.adaptive_snapshot_extreme_clients` / `network.adaptive_snapshot_extreme_rate`: final cap for 45-50 player servers. This deliberately favors command/ping responsiveness over visual update frequency.
- `network.slow_client_snapshot_stride`: per-client snapshot stride used while a client is marked slow by outbound queue delay.
- `network.slow_client_outbox_wait_ms`: marks a client slow when a packet waited this long in its output queue.
- `network.slow_client_recovery_seconds`: how long slow-client snapshot throttling remains active after a backpressure spike.
- `network.connection_burst_window_seconds`, `network.connection_burst_threshold` and `network.connection_burst_snapshot_rate`: temporarily lower snapshot fan-out while many TCP clients are connecting at once.
- `network.state_hash_sample_seconds`: minimum interval between server-side snapshot hashes stored for desync checks. Hashing is intentionally sampled because stable JSON hashing is expensive.
- `network.full_snapshot_interval_seconds`: how often each client receives a full resync even when delta snapshots are working.
- `network.resume_timeout_seconds`: how long a disconnected player remains in the world and can resume with the same `session_token`.
- `network.journal_seconds`: retention window for recent command results, gameplay events and snapshot metadata used by reconnect/replay diagnostics.
- `network.write_buffer_high_water` and `network.write_buffer_low_water`: asyncio transport backpressure thresholds. Higher values absorb short fan-out bursts; stale realtime snapshots are still capped by `max_pending_snapshots_per_client`.
- `rate_limits.input_per_second`: maximum movement input messages accepted from one player per second.
- `rate_limits.command_per_second`: maximum reliable command messages accepted from one player per second.
- `rate_limits.inbound_bytes_per_second`: maximum inbound bytes accepted from one connected player per second before closing the connection.
- `observability.enabled`: starts or disables the lightweight HTTP probe server.
- `observability.host` and `observability.port`: bind address for `/metrics`, `/health` and `/ready`.
- If the observability port is already occupied, the game TCP server still starts and logs that HTTP probes are disabled for that process.
- `profiling.log_interval_seconds`: interval for `python -m server.main --profile` metrics.
- `profiling.slow_tick_ms` and `profiling.slow_snapshot_ms`: reserved thresholds for stricter profiling alerts.

The TCP protocol uses length-prefixed frames. `msgpack` is used when installed; otherwise the same framing falls back to compact JSON. Snapshot packets are treated as lossy/unreliable inside the server queue, so stale snapshots can be dropped for slow clients. Login, profile updates, transactional commands, pings, command results and gameplay events stay on the reliable queue.

The server reuses a snapshot interest index within the same simulation tick. This avoids rebuilding the spatial index repeatedly during connection bursts, reconnects and snapshot fan-out.

Clients start with a versioned `hello` handshake containing `client_version`, `protocol_version`, `snapshot_schema` and supported features. The server answers with `welcome`, including `session_token`, `resume_timeout`, `mode`, `pvp`, server features and a lightweight bootstrap snapshot containing the local player. The normal snapshot pipeline fills nearby world state immediately after that, which keeps burst joins cheap. After a short connection drop, the client sends `resume` with `player_id`, `session_token` and `last_snapshot_tick`; the server restores the same player when the token is still valid and sends a filtered full snapshot.

Start a PvP server with `python -m server.main --mode pvp` or `--pvp`. In PvP mode the server sets `initial_zombies=0`, `max_zombies=0`, does not start zombie AI workers, and advertises `pvp=true` in ping/ready/welcome payloads so the client can badge the server list.

Snapshot messages include:

- `tick`: authoritative server simulation tick.
- `seq`: server snapshot sequence for this client.
- `ack_input_seq`: last client input sequence processed by the server.
- `server_time`: authoritative world time used by interpolation buffers.
- `snapshot_interval`: expected time between snapshots.
- `schema`: currently `compact-v1`.

`compact-v1` keeps the local player as a full player object for inventory/HUD correctness, while remote players, zombies, projectiles, grenades, mines, poison pools and loot are sent as compact arrays. The client expands this schema back into the shared `WorldSnapshot` model.

Gameplay events are delivered separately with message type `events`. They are meant for one-shot effects and UI feedback such as `shot`, `hit`, `player_died`, `zombie_killed`, `grenade_exploded`, `mine_exploded` and `item_picked`.

Movement input and gameplay commands are intentionally separate:

- `input`: frequent disposable state containing only movement, aim, shooting, sprint and sneak.
- `command`: reliable ordered transaction with `command_id`, `kind` and `payload`.
- `command_result`: authoritative result for exactly one command, including `ok`, `reason` when rejected, and `server_tick`.

Current command kinds include `pickup`, `interact`, `inventory_action`, `craft`, `repair`, `equip_armor`, `select_slot`, `reload`, `throw_grenade`, `toggle_utility`, `use_medkit` and `respawn`. Movement input may be overwritten by a newer input before the next simulation tick; commands are queued and processed in order.

## Observability Endpoints

When `observability.enabled` is true, the server exposes:

- `/health`: returns HTTP 200 while the Python process and HTTP probe are alive. It reports `healthy` or `shutting_down`.
- `/ready`: returns HTTP 200 only when the server accepts players, the simulation loop is alive, persistence is running and `network.max_clients` is not reached. Otherwise it returns HTTP 503.
- `/metrics`: Prometheus text format for runtime metrics.

The normal game-server ping response also includes `ready`, `max_players`, `tick_rate`, `snapshot_rate` and `metrics_url`, so the client server list can show readiness without opening the HTTP port directly.

Main `/metrics` series:

- `neon_connected_players`: currently connected players.
- `neon_effective_snapshot_rate`: currently active adaptive snapshot rate after player-count caps.
- `neon_tick_ms_avg`, `neon_tick_ms_p95`, `neon_tick_ms_p99`, plus `neon_tick_ms{quantile="avg|p95|p99"}` and `neon_tick_ms_count`: simulation tick duration. Rising p95/p99 means AI, physics, commands or world update cost is too high.
- `neon_snapshot_ms_avg`, `neon_snapshot_ms_p95`, `neon_snapshot_ms_p99`, plus `neon_snapshot_ms{quantile="avg|p95|p99"}` and `neon_snapshot_ms_count`: snapshot build/filter/queue loop duration. Rising values point to interest filtering, delta encoding or per-client queue pressure.
- `neon_command_ack_ms_avg`, `neon_command_ack_ms_p95`, `neon_command_ack_ms_p99`, plus `neon_command_ack_ms{quantile="avg|p95|p99"}` and `neon_command_ack_ms_count`: server-side reliable command processing latency from receive to result generation.
- `neon_world_update_ms_*`: cost of world update, zombie movement, combat, projectiles and collisions.
- `neon_command_apply_ms_*`: cost of applying queued reliable commands inside the simulation tick.
- `neon_input_apply_ms_*`: cost of applying latest movement inputs inside the simulation tick.
- `neon_snapshot_collect_ms_*`: cost of collecting the authoritative world snapshot from simulation state.
- `neon_interest_filter_ms_*`: cost of per-client interest filtering and snapshot preparation for the served batch.
- `neon_delta_build_ms_*`: cost of comparing the current filtered snapshot with the previous client snapshot.
- `neon_compact_encode_ms_*`: cost of compact schema packing plus protocol frame encoding.
- `neon_transport_write_ms_*`: time spent writing packets to asyncio transports and waiting for backpressure.
- `neon_outbox_wait_ms_*`: time packets spent inside per-client output queues before the writer sends them. High values mean queue pressure is delaying control or snapshot delivery.

Local-player delta snapshots send inventory/equipment as a full player payload only when those heavy fields change. Ordinary movement, aim, health, armor and active-weapon updates stay in the compact row schema to keep snapshot traffic low.

- `neon_commands_rejected_total`: invalid, rate-limited or game-rule rejected commands.
- `neon_reconnect_total`: successful resume handshakes.
- `neon_dropped_snapshots_total`: stale snapshot packets dropped from slow-client queues.
- `neon_skipped_snapshots_total`: snapshot builds skipped before interest filtering because a client was already backpressured.
- `neon_bytes_sent_total` and `neon_bytes_received_total`: raw game-protocol traffic counters.
- `neon_desync_reports_total`: client snapshot hashes received by the desync detector.
- `neon_desync_mismatch_total`: mismatched client/server hashes.
- `neon_desync_forced_full_total`: full snapshots forced after detected desync.
- `neon_rate_limited_inputs_total`, `neon_rate_limited_commands_total`, `neon_rate_limited_bytes_total`: rate-limit pressure by category.
- `neon_resume_tickets`: disconnected players still resumable.
- `neon_output_queue_packets`: total queued outbound packets across connected clients.
- `neon_slow_clients`: clients currently under slow-client snapshot throttling.
- `neon_connection_burst_count`: accepted TCP connections currently inside the burst-detection window.
- `neon_persistence_queue_size`: records waiting for the persistence worker.

Python/process-specific metrics:

- `neon_process_uptime_seconds`: process uptime.
- `neon_process_cpu_seconds_total`: Python process CPU time.
- `neon_python_threads`: active Python threads, useful for checking worker leaks.
- `neon_python_gc_count{generation="0|1|2"}`: current GC generation counters.
- `neon_asyncio_tasks`: active asyncio tasks in the server loop.
- `neon_python_allocated_blocks`: CPython allocated memory blocks when available.
- `neon_process_pid`: OS process id for correlating with external profilers.

## Desync Detector

The online client periodically sends:

```json
{
  "type": "state_hash",
  "tick": 12000,
  "hash": "..."
}
```

The hash is calculated from the latest authoritative snapshot stored by the network client, not from the predicted/interpolated render state. The server compares it with the hash of the snapshot that was actually queued to that player. On mismatch, the server increments desync metrics, forces the next snapshot to be full and sends `state_hash_result` with `force_full: true`.

The server keeps short command/event/snapshot journals for resume replay and desync debugging. Persistent records are written by a background worker into `server_data/` as JSON/JSONL files, outside the game tick:

- `player_profiles.json`: latest player position, stats, inventory, equipment and weapons.
- `session_history.jsonl`: connect, disconnect, resume and shutdown history.
- `match_events.jsonl`: command results and gameplay events.

On SIGTERM/SIGINT-capable platforms, the server stops accepting new clients, sends `server_shutdown`, saves active player profiles and closes connections cleanly.
