package game

import "neonoutbreak/server_go/shared"

const (
	PlayerRadius     = shared.PlayerRadius
	ZombieRadius     = shared.ZombieRadius
	ZombieHitRadius  = shared.ZombieHitRadius
	WalkNoise        = shared.WalkNoise
	SprintNoise      = shared.SprintNoise
	ShotNoise        = shared.ShotNoise
	SprintMultiplier = shared.SprintMultiplier
)

type Vec2 = shared.Vec2
type Input = shared.InputCommand
type Weapon = shared.WeaponRuntime
type Player = shared.PlayerState
type Zombie = shared.ZombieState
type Projectile = shared.ProjectileState
type Grenade = shared.GrenadeState
type Mine = shared.MineState
type PoisonProjectile = shared.PoisonProjectileState
type PoisonPool = shared.PoisonPoolState
type Loot = shared.LootState
type Building = shared.BuildingState
type Snapshot = shared.WorldSnapshot

type Command struct {
	PlayerID   string
	CommandID  int64
	Kind       string
	Payload    map[string]any
	ResultFunc func(CommandResult)
}

type CommandResult struct {
	PlayerID   string
	CommandID  int64
	Kind       string
	OK         bool
	Reason     string
	ServerTick int64
}

type RuntimeStats struct {
	ConnectedPlayers int64
	TotalPlayers     int64
	Zombies          int64
	TickMS           float64
	SnapshotMS       float64
	BytesIn          uint64
	BytesOut         uint64
	DroppedSnapshots uint64
	CommandsRejected uint64
	Reconnects       uint64
}
