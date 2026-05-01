package shared

import (
	"math"
	"time"
)

const (
	MapWidth         = 28800.0
	MapHeight        = 19800.0
	TickRate         = 30
	SnapshotRate     = 20
	PlayerRadius     = 24.0
	ZombieRadius     = 24.0
	ZombieHitRadius  = 34.0
	PickupRadius     = 72.0
	InteractRadius   = 86.0
	SearchDuration   = 5.0
	SneakNoise       = 70.0
	WalkNoise        = 230.0
	SprintNoise      = 520.0
	ShotNoise        = 850.0
	SprintMultiplier = 1.72
)

var Slots = []string{"1", "2", "3", "4", "5", "6", "7", "8", "9", "0"}
var EquipmentSlots = []string{"head", "torso", "legs", "arms"}

type Vec2 struct {
	X float64 `json:"x"`
	Y float64 `json:"y"`
}

func (v Vec2) Copy() Vec2 {
	return Vec2{X: v.X, Y: v.Y}
}

func (v Vec2) ToMap() map[string]float64 {
	return map[string]float64{"x": Round(v.X, 3), "y": Round(v.Y, 3)}
}

func (v Vec2) Distance(to Vec2) float64 {
	return math.Hypot(v.X-to.X, v.Y-to.Y)
}

func (v Vec2) AngleTo(to Vec2) float64 {
	return math.Atan2(to.Y-v.Y, to.X-v.X)
}

func (v Vec2) Add(to Vec2) Vec2 {
	return Vec2{X: v.X + to.X, Y: v.Y + to.Y}
}

func (v Vec2) Mul(scale float64) Vec2 {
	return Vec2{X: v.X * scale, Y: v.Y * scale}
}

func (v Vec2) Length() float64 {
	return math.Hypot(v.X, v.Y)
}

func (v Vec2) Normalize() Vec2 {
	length := v.Length()
	if length <= 0.0001 {
		return Vec2{}
	}
	return Vec2{X: v.X / length, Y: v.Y / length}
}

func (v Vec2) ClampToMap(width, height float64) Vec2 {
	return Vec2{X: Clamp(v.X, 0, width), Y: Clamp(v.Y, 0, height)}
}

type RectState struct {
	X float64 `json:"x"`
	Y float64 `json:"y"`
	W float64 `json:"w"`
	H float64 `json:"h"`
}

func (r RectState) Center() Vec2 {
	return Vec2{X: r.X + r.W*0.5, Y: r.Y + r.H*0.5}
}

func (r RectState) Contains(pos Vec2) bool {
	return r.X <= pos.X && pos.X <= r.X+r.W && r.Y <= pos.Y && pos.Y <= r.Y+r.H
}

func (r RectState) Inflated(amount float64) RectState {
	return RectState{X: r.X - amount, Y: r.Y - amount, W: r.W + amount*2, H: r.H + amount*2}
}

func (r RectState) ToMap() map[string]float64 {
	return map[string]float64{
		"x": Round(r.X, 3),
		"y": Round(r.Y, 3),
		"w": Round(r.W, 3),
		"h": Round(r.H, 3),
	}
}

type DoorState struct {
	ID    string    `json:"id"`
	Rect  RectState `json:"rect"`
	Open  bool      `json:"open"`
	Floor int       `json:"floor"`
}

func (d DoorState) ToMap() map[string]any {
	return map[string]any{"id": d.ID, "rect": d.Rect.ToMap(), "open": d.Open, "floor": d.Floor}
}

type PropState struct {
	ID     string    `json:"id"`
	Kind   string    `json:"kind"`
	Rect   RectState `json:"rect"`
	Floor  int       `json:"floor"`
	Blocks bool      `json:"blocks"`
}

func (p PropState) ToMap() map[string]any {
	return map[string]any{"id": p.ID, "kind": p.Kind, "rect": p.Rect.ToMap(), "floor": p.Floor, "blocks": p.Blocks}
}

type BuildingState struct {
	ID       string      `json:"id"`
	Name     string      `json:"name"`
	Bounds   RectState   `json:"bounds"`
	Walls    []RectState `json:"walls"`
	Doors    []DoorState `json:"doors"`
	Props    []PropState `json:"props"`
	Stairs   []RectState `json:"stairs"`
	Floors   int         `json:"floors"`
	MinFloor int         `json:"min_floor"`
}

func (b BuildingState) MaxFloor() int {
	return b.MinFloor + b.Floors - 1
}

func (b BuildingState) ToMap() map[string]any {
	walls := make([]any, 0, len(b.Walls))
	for _, wall := range b.Walls {
		walls = append(walls, wall.ToMap())
	}
	doors := make([]any, 0, len(b.Doors))
	for _, door := range b.Doors {
		doors = append(doors, door.ToMap())
	}
	props := make([]any, 0, len(b.Props))
	for _, prop := range b.Props {
		props = append(props, prop.ToMap())
	}
	stairs := make([]any, 0, len(b.Stairs))
	for _, stair := range b.Stairs {
		stairs = append(stairs, stair.ToMap())
	}
	return map[string]any{
		"id":        b.ID,
		"name":      b.Name,
		"bounds":    b.Bounds.ToMap(),
		"walls":     walls,
		"doors":     doors,
		"props":     props,
		"stairs":    stairs,
		"floors":    b.Floors,
		"min_floor": b.MinFloor,
	}
}

func CloneBuilding(src *BuildingState) *BuildingState {
	if src == nil {
		return nil
	}
	cp := *src
	cp.Walls = append([]RectState(nil), src.Walls...)
	cp.Doors = append([]DoorState(nil), src.Doors...)
	cp.Props = append([]PropState(nil), src.Props...)
	cp.Stairs = append([]RectState(nil), src.Stairs...)
	return &cp
}

type ItemSpec struct {
	Key           string
	Title         string
	Kind          string
	StackSize     int
	HealTotal     int
	HealSeconds   float64
	EquipmentSlot string
	ArmorKey      string
	Color         [3]int
}

type RecipeSpec struct {
	Key       string
	Title     string
	Requires  map[string]int
	ResultKey string
	ResultQty int
}

type WeaponSpec struct {
	Key             string  `json:"key"`
	Title           string  `json:"title"`
	Slot            string  `json:"slot"`
	Damage          int     `json:"damage"`
	MagazineSize    int     `json:"magazine_size"`
	FireRate        float64 `json:"fire_rate"`
	ReloadTime      float64 `json:"reload_time"`
	ProjectileSpeed float64 `json:"projectile_speed"`
	Spread          float64 `json:"spread"`
	Pellets         int     `json:"pellets"`
}

type ArmorSpec struct {
	Key         string  `json:"key"`
	Title       string  `json:"title"`
	Mitigation  float64 `json:"mitigation"`
	ArmorPoints int     `json:"armor_points"`
}

type ZombieSpec struct {
	Key           string  `json:"key"`
	Title         string  `json:"title"`
	Health        int     `json:"health"`
	Armor         int     `json:"armor"`
	Speed         float64 `json:"speed"`
	Damage        int     `json:"damage"`
	Radius        float64 `json:"radius"`
	Color         [3]int  `json:"color"`
	SightRange    float64 `json:"sight_range"`
	HearingRange  float64 `json:"hearing_range"`
	FOVDegrees    float64 `json:"fov_degrees"`
	Sensitivity   float64 `json:"sensitivity"`
	SuspicionTime float64 `json:"suspicion_time"`
}

type RaritySpec struct {
	Key                        string
	Title                      string
	Color                      [3]int
	LootWeight                 float64
	WeaponDamageMultiplier     float64
	WeaponDurabilityMultiplier float64
	ArmorPointsMultiplier      float64
	ArmorMitigationMultiplier  float64
	ArmorDurabilityMultiplier  float64
}

type GrenadeSpec struct {
	Key               string
	Title             string
	Timer             float64
	Contact           bool
	ThrowDistance     float64
	BlastRadius       float64
	ZombieDamage      int
	ZombieDamageBonus int
	PlayerDamage      int
	PlayerDamageBonus int
}

type MineSpec struct {
	Key               string
	Title             string
	TriggerRadius     float64
	BlastRadius       float64
	ZombieDamage      int
	ZombieDamageBonus int
	PlayerDamage      int
	PlayerDamageBonus int
}

type WeaponModuleSpec struct {
	Key                string
	Title              string
	Slot               string
	BeamLength         float64
	ConeRange          float64
	ConeDegrees        float64
	SpreadMultiplier   float64
	MagazineMultiplier float64
	NoiseMultiplier    float64
	FireRateBonus      float64
	FireRateRarityStep float64
}

type StartingWeapon struct {
	Key         string
	ReserveAmmo int
}

type StartingItem struct {
	Key    string
	Amount int
}

type BackpackConfig struct {
	Slots          int
	StartingWeapon StartingWeapon
	StartingItems  []StartingItem
}

type WeightedLoot struct {
	Key    string
	Min    int
	Weight float64
}

type InventoryItem struct {
	ID         string  `json:"id"`
	Key        string  `json:"key"`
	Amount     int     `json:"amount"`
	Durability float64 `json:"durability"`
	Rarity     string  `json:"rarity"`
}

func (i *InventoryItem) ToMap() map[string]any {
	if i == nil {
		return nil
	}
	return map[string]any{
		"id":         i.ID,
		"key":        i.Key,
		"amount":     i.Amount,
		"durability": Round(i.Durability, 2),
		"rarity":     i.Rarity,
	}
}

type WeaponRuntime struct {
	Key         string         `json:"key"`
	AmmoInMag   int            `json:"ammo_in_mag"`
	ReserveAmmo int            `json:"reserve_ammo"`
	Cooldown    float64        `json:"cooldown"`
	ReloadLeft  float64        `json:"reload_left"`
	Durability  float64        `json:"durability"`
	Rarity      string         `json:"rarity"`
	Modules     map[string]any `json:"modules"`
	UtilityOn   bool           `json:"utility_on"`
}

func NewWeaponRuntime(spec WeaponSpec, reserveAmmo int, rarity string) *WeaponRuntime {
	if rarity == "" {
		rarity = "common"
	}
	return &WeaponRuntime{
		Key:         spec.Key,
		AmmoInMag:   spec.MagazineSize,
		ReserveAmmo: reserveAmmo,
		Durability:  100,
		Rarity:      rarity,
		Modules:     map[string]any{"utility": nil, "magazine": nil},
	}
}

func (w *WeaponRuntime) ToMap() map[string]any {
	if w == nil {
		return nil
	}
	modules := map[string]any{"utility": nil, "magazine": nil}
	for key, value := range w.Modules {
		modules[key] = value
	}
	return map[string]any{
		"key":          w.Key,
		"ammo_in_mag":  w.AmmoInMag,
		"reserve_ammo": w.ReserveAmmo,
		"cooldown":     Round(w.Cooldown, 3),
		"reload_left":  Round(w.ReloadLeft, 3),
		"durability":   Round(w.Durability, 2),
		"rarity":       w.Rarity,
		"modules":      modules,
		"utility_on":   w.UtilityOn,
	}
}

type PlayerState struct {
	ID                string
	Name              string
	Pos               Vec2
	Angle             float64
	Health            int
	Armor             int
	ArmorKey          string
	Speed             float64
	ActiveSlot        string
	Alive             bool
	Score             int
	KillsByKind       map[string]int
	Medkits           int
	OwnedArmors       []string
	Noise             float64
	Sprinting         bool
	Sneaking          bool
	Floor             int
	InsideBuilding    any
	Backpack          []*InventoryItem
	Equipment         map[string]*InventoryItem
	QuickItems        map[string]*InventoryItem
	HealingLeft       float64
	HealingRate       float64
	HealingPool       float64
	HealingStacks     int
	PoisonLeft        float64
	PoisonTick        float64
	PoisonDamage      int
	MeleeCooldown     float64
	Notice            string
	NoticeTimer       float64
	PingMS            int
	ConnectionQuality string
	Weapons           map[string]*WeaponRuntime
	UpdatedAt         time.Time
}

func (p *PlayerState) ActiveWeapon() *WeaponRuntime {
	if p == nil {
		return nil
	}
	return p.Weapons[p.ActiveSlot]
}

type ZombieState struct {
	ID              string
	Kind            string
	Pos             Vec2
	Health          int
	Armor           int
	Mode            string
	Facing          float64
	TargetPlayerID  string
	LastKnown       Vec2
	HasLastKnown    bool
	Waypoint        Vec2
	HasWaypoint     bool
	SearchTimer     float64
	Alertness       float64
	IdleTimer       float64
	SpecialCooldown float64
	StrafePhase     float64
	SidestepBias    float64
	SidestepTimer   float64
	AttackCooldown  float64
	DecisionDue     float64
	Generation      int64
	Floor           int
	InsideBuilding  any
}

type ProjectileState struct {
	ID        string
	OwnerID   string
	Pos       Vec2
	Velocity  Vec2
	Damage    int
	Life      float64
	Radius    float64
	Floor     int
	WeaponKey string
}

type GrenadeState struct {
	ID       string
	OwnerID  string
	Pos      Vec2
	Velocity Vec2
	Timer    float64
	Floor    int
	Radius   float64
	Kind     string
}

type MineState struct {
	ID            string
	OwnerID       string
	Kind          string
	Pos           Vec2
	Floor         int
	Armed         bool
	TriggerRadius float64
	BlastRadius   float64
	Rotation      float64
}

type PoisonProjectileState struct {
	ID       string
	OwnerID  string
	Pos      Vec2
	Velocity Vec2
	Target   Vec2
	Floor    int
	Radius   float64
	Life     float64
}

type PoisonPoolState struct {
	ID     string
	Pos    Vec2
	Floor  int
	Timer  float64
	Radius float64
}

type LootState struct {
	ID      string
	Kind    string
	Pos     Vec2
	Payload string
	Amount  int
	Floor   int
	Rarity  string
}

type InputCommand struct {
	Seq      int64
	PlayerID string
	MoveX    float64
	MoveY    float64
	AimX     float64
	AimY     float64
	Shooting bool
	Sprint   bool
	Sneak    bool
}

type ClientCommand struct {
	PlayerID  string
	CommandID int64
	Kind      string
	Payload   map[string]any
}

type WorldSnapshot struct {
	Tick              int64
	Time              float64
	MapWidth          float64
	MapHeight         float64
	Players           map[string]*PlayerState
	Zombies           map[string]*ZombieState
	Projectiles       map[string]*ProjectileState
	Grenades          map[string]*GrenadeState
	Mines             map[string]*MineState
	PoisonProjectiles map[string]*PoisonProjectileState
	PoisonPools       map[string]*PoisonPoolState
	Loot              map[string]*LootState
	Buildings         map[string]*BuildingState
}

func Clamp(value, low, high float64) float64 {
	return math.Max(low, math.Min(high, value))
}

func Round(value float64, precision int) float64 {
	scale := math.Pow10(precision)
	return math.Round(value*scale) / scale
}

func SlotExists(slot string) bool {
	for _, candidate := range Slots {
		if candidate == slot {
			return true
		}
	}
	return false
}
