# Neon Outbreak Go Server

High-performance Go implementation of the online server. It is intentionally isolated from the Python server so both can coexist while the Go runtime is hardened.

## Requirements

- Recommended: Go 1.26.2 or newer from the official Go 1.26 release line.
- The code uses only the Go standard library. No module download is required.
- Local note: the project was formatted and build-checked with the available Go toolchain in this workspace.

## Quick Start

From the repository root:

```powershell
cd server_go
go test ./...
go build -trimpath -buildvcs=false -o bin\neon-server.exe .\cmd\neon-server
.\bin\neon-server.exe --config configs\server.json
```

Run a PvP server without zombies:

```powershell
cd server_go
go build -trimpath -buildvcs=false -o bin\neon-server.exe .\cmd\neon-server
.\bin\neon-server.exe --config configs\server.json --mode pvp --port 8768
```

Run a PvE server with explicit AI workers:

```powershell
cd server_go
.\bin\neon-server.exe --mode survival --zombie-workers 4 --max-clients 50
```

The Python client can add the Go server to `servers.json` the same way as the Python server. The Go server uses the same length-prefixed TCP framing and protocol version `2`.

## Protocol Compatibility

The Go server accepts:

- `ping`
- `hello`
- `resume`
- `input`
- `command`
- `profile`
- `state_hash`

Incoming frames can be JSON or msgpack. The server includes a small msgpack decoder for the client handshake/input path because the Python client often sends msgpack when the package is installed. Outgoing frames are length-prefixed JSON; the Python client already supports JSON frames even when msgpack is available.

Snapshots are sent with schema `compact-v1`, using the same compact keys as the Python server:

- `lp`: local player full state
- `p`: other players
- `z`: zombies
- `s`: projectiles
- `g`, `m`, `pp`, `pl`: grenades, mines and poison entities
- `l`: loot/items
- `b`: building, door, prop, stair and tunnel geometry

## Shared Gameplay Layer

The package `server_go/shared` mirrors the Python `shared` modules and is safe to import from
future Go clients, including an Ebitengine client:

- shared gameplay models and `compact-v1` network schema
- config-backed weapons, armor, zombies, rarities, backpack, explosives and modules
- building/floor/tunnel geometry
- circle-vs-rect collision and line-of-sight helpers
- snapshot hashing for desync checks

The authoritative server code in `internal/game` now consumes this shared layer instead of
owning separate copies of the map, item, collision and snapshot contracts.

## Architecture

```text
TCP accept loop
  -> per-client reader goroutine
  -> per-client priority writer goroutine
       control queue: welcome, pong, command_result
       snapshot queue: max 1 realtime snapshot

simulation loop
  fixed tick
  input channel drain, last input wins
  reliable command channel drain
  player movement/combat
  projectile/zombie collision
  zombie movement

AI worker pool
  receives immutable decision tasks
  performs sight/hearing decision work
  returns decisions with generation ids
  world applies valid decisions only

snapshot loop
  fixed snapshot rate
  interest filtering per player
  compact-v1 snapshot payload

HTTP probe
  /health
  /ready
  /metrics
```

The HTTP probe is implemented separately in `internal/observability`, not inside the game server. It can be disabled with `metrics_enabled=false`.

## Why Go Here

- One goroutine per client reader and writer keeps network backpressure isolated.
- Control packets are prioritized over snapshots, so `pong` and `command_result` do not sit behind stale world state.
- Each client keeps only one pending snapshot. Old realtime snapshots are replaced.
- Simulation remains authoritative and single-writer, which avoids lock-heavy world mutation.
- Zombie AI decisions are moved to worker goroutines, while movement/collisions remain in the authoritative simulation loop.
- AI decisions carry generation ids, so stale worker decisions cannot overwrite newer reactions like damage alerts.

## Configuration

`configs/server.json` contains:

- `mode`: `survival` or `pvp`
- `max_clients`: intended cap, currently tuned for 4-10 stable players and up to 50
- `tick_rate`: authoritative simulation rate
- `snapshot_rate`: outbound world update rate
- `interest_radius`: radius used for per-client snapshot filtering
- `initial_zombies`, `max_zombies`: ignored in PvP mode
- `zombie_ai_workers`: number of AI worker goroutines
- `zombie_ai_decision_rate`: near-player bot decision rate
- `zombie_ai_far_decision_rate`: far bot decision rate
- `zombie_ai_active_radius`, `zombie_ai_far_radius`: AI spatial filters
- `output_queue_packets`: reliable control queue size per client
- `resume_timeout_seconds`: reconnect window
- `metrics_enabled`: enables the lightweight Prometheus/health HTTP server
- `metrics_host`, `metrics_port`: HTTP probe bind

## Health, Ready And Prometheus

When `metrics_enabled=true`, the Go server starts a separate lightweight HTTP server:

```text
GET /health   process liveness
GET /ready    readiness, accepting player state, mode, player/zombie counts
GET /metrics  Prometheus text format
```

Important metrics:

- `neon_connected_players`
- `neon_world_players`
- `neon_resume_tickets`
- `neon_zombies`
- `neon_tick_ms_avg`, `neon_tick_ms_p95`, `neon_tick_ms_p99`
- `neon_snapshot_ms_avg`, `neon_snapshot_ms_p95`, `neon_snapshot_ms_p99`
- `neon_command_ack_ms_avg`, `neon_command_ack_ms_p95`, `neon_command_ack_ms_p99`
- `neon_commands_rejected_total`
- `neon_reconnect_total`
- `neon_dropped_snapshots_total`
- `neon_bytes_sent_total`
- `neon_bytes_received_total`
- `neon_go_goroutines`
- `neon_go_heap_alloc_bytes`
- `neon_go_gc_cycles_total`

## Current Gameplay Coverage

Implemented now:

- authoritative player movement
- sprint/sneak noise
- shooting/projectiles
- map buildings, floors, doors, props and basement tunnels in snapshots
- server-side wall/door/prop collision using the shared collision solver
- loot spawning, pickup, backpack stacks and quick weapon/explosive slots
- inventory move/drop/use, armor equipment, repair kits and basic crafting commands
- grenades and mines with owner kill credit
- zombie patrol, investigate, chase, search
- zombie reaction to player shots with shared config-backed sight/hearing settings
- player damage/death/respawn command
- PvE/PvP mode split
- reconnect/resume token path
- ping/server-list metadata including PvP flag
- Prometheus-style metrics endpoint
