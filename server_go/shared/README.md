# Shared Gameplay Layer

`server_go/shared` is the common gameplay contract for the Go server and a future Go client
based on Ebitengine.

The package mirrors the Python `shared` modules:

- `models.go` contains map, inventory, weapon, armor, loot, projectile, zombie and snapshot models.
- `content.go` loads gameplay data from the root `configs` directory and keeps sane defaults.
- `level.go` builds the same house, floor, door, prop and basement tunnel geometry.
- `collision.go` ports the circle-vs-rect movement solver used by the Python client/server.
- `net_schema.go` emits `compact-v1` snapshots compatible with the current Python client.
- `state_hash.go` provides a short deterministic snapshot hash for desync checks.

The server should keep authoritative simulation in `internal/game`, but any model or pure
gameplay rule that the client also needs should live here first. This keeps the Python client
compatible today and leaves a clean import path for a future Go client:

```go
import "neonoutbreak/server_go/shared"
```

Configuration discovery checks `../configs`, `configs`, `../../configs`, then
`server_go/configs`, so the server works when started from either the repository root or
the `server_go` directory.
