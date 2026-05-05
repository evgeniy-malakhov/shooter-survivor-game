package game

import (
	"math"
	"math/rand"
	"runtime"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"neonoutbreak/server_go/internal/config"
	"neonoutbreak/server_go/shared"
)

type World struct {
	cfg     config.Config
	content *shared.Content

	mu          sync.RWMutex
	rng         *rand.Rand
	nextID      atomic.Int64
	tick        atomic.Int64
	worldTime   float64
	players     map[string]*Player
	zombies     map[string]*Zombie
	projectiles map[string]*Projectile
	grenades    map[string]*Grenade
	mines       map[string]*Mine
	poisonShots map[string]*PoisonProjectile
	poisonPools map[string]*PoisonPool
	loot        map[string]*Loot
	buildings   map[string]*Building
	inputs      map[string]Input

	commands         chan Command
	inputCh          chan Input
	ai               *AIWorkerPool
	stats            *RuntimeStats
	grenadeCooldowns map[string]float64
}

func NewWorld(cfg config.Config, stats *RuntimeStats) *World {
	content, _ := shared.LoadContent("")
	if content == nil {
		content = shared.DefaultContent()
	}
	w := &World{
		cfg:              cfg,
		content:          content,
		rng:              rand.New(rand.NewSource(time.Now().UnixNano())),
		players:          map[string]*Player{},
		zombies:          map[string]*Zombie{},
		projectiles:      map[string]*Projectile{},
		grenades:         map[string]*Grenade{},
		mines:            map[string]*Mine{},
		poisonShots:      map[string]*PoisonProjectile{},
		poisonPools:      map[string]*PoisonPool{},
		loot:             map[string]*Loot{},
		buildings:        shared.MakeBuildings(),
		inputs:           map[string]Input{},
		inputCh:          make(chan Input, 8192),
		commands:         make(chan Command, 4096),
		stats:            stats,
		grenadeCooldowns: map[string]float64{},
	}
	workers := cfg.ZombieAIWorkers
	if workers <= 0 && cfg.Mode != "pvp" {
		workers = max(1, min(2, runtime.NumCPU()/2))
	}
	w.ai = NewAIWorkerPool(workers)
	w.primeMap()
	return w
}

func (w *World) Close() {
	if w.ai != nil {
		w.ai.Close()
	}
}

func (w *World) QueueInput(input Input) {
	select {
	case w.inputCh <- input:
	default:
	}
}

func (w *World) QueueCommand(command Command) bool {
	select {
	case w.commands <- command:
		return true
	default:
		if command.ResultFunc != nil {
			command.ResultFunc(CommandResult{PlayerID: command.PlayerID, CommandID: command.CommandID, Kind: command.Kind, OK: false, Reason: "command_queue_full", ServerTick: w.tick.Load()})
		}
		return false
	}
}

func (w *World) AddPlayer(name string, requestedID string) *Player {
	w.mu.Lock()
	defer w.mu.Unlock()
	id := requestedID
	if id == "" {
		id = w.id("p")
	}
	p := &Player{
		ID:                id,
		Name:              cleanName(name),
		Pos:               w.randomOpenPos(true),
		Health:            100,
		ArmorKey:          "none",
		Speed:             245,
		ActiveSlot:        "1",
		Alive:             true,
		KillsByKind:       map[string]int{},
		OwnedArmors:       []string{"none"},
		ConnectionQuality: "stable",
		Weapons:           map[string]*Weapon{},
		Backpack:          make([]*shared.InventoryItem, w.content.Backpack.Slots),
		Equipment:         map[string]*shared.InventoryItem{"head": nil, "torso": nil, "legs": nil, "arms": nil},
		QuickItems:        map[string]*shared.InventoryItem{},
		UpdatedAt:         time.Now(),
	}
	for kind := range w.content.Zombies {
		p.KillsByKind[kind] = 0
	}
	for _, slot := range shared.Slots {
		p.QuickItems[slot] = nil
	}
	weaponKey := w.content.Backpack.StartingWeapon.Key
	spec, ok := w.content.Weapons[weaponKey]
	if !ok {
		spec = w.content.Weapons["pistol"]
	}
	p.Weapons[spec.Slot] = shared.NewWeaponRuntime(spec, w.content.Backpack.StartingWeapon.ReserveAmmo, "common")
	p.ActiveSlot = spec.Slot
	for _, item := range w.content.Backpack.StartingItems {
		_ = w.addItem(p, item.Key, item.Amount, "common")
	}
	w.players[id] = p
	w.inputs[id] = Input{PlayerID: id, AimX: p.Pos.X + 1, AimY: p.Pos.Y}
	w.grenadeCooldowns[id] = 0
	atomic.StoreInt64(&w.stats.TotalPlayers, int64(len(w.players)))
	return clonePlayer(p)
}

func (w *World) RemovePlayerInput(playerID string) {
	w.mu.Lock()
	defer w.mu.Unlock()
	delete(w.inputs, playerID)
}

func (w *World) RemovePlayer(playerID string) {
	w.mu.Lock()
	defer w.mu.Unlock()
	delete(w.players, playerID)
	delete(w.inputs, playerID)
	delete(w.grenadeCooldowns, playerID)
	atomic.StoreInt64(&w.stats.TotalPlayers, int64(len(w.players)))
}

func (w *World) RenamePlayer(playerID, name string) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if p := w.players[playerID]; p != nil {
		p.Name = cleanName(name)
	}
}

func (w *World) Tick(dt float64) {
	start := time.Now()
	w.mu.Lock()
	w.worldTime += dt
	w.drainInputs()
	w.drainCommands()
	w.updatePlayers(dt)
	w.updateProjectiles(dt)
	w.updateGrenades(dt)
	w.updateMines(dt)
	w.drainAI()
	w.scheduleAI()
	w.updateZombies(dt)
	w.tick.Add(1)
	atomic.StoreInt64(&w.stats.Zombies, int64(len(w.zombies)))
	w.mu.Unlock()
	w.stats.TickMS = float64(time.Since(start).Microseconds()) / 1000
}

func (w *World) Snapshot() Snapshot {
	w.mu.RLock()
	defer w.mu.RUnlock()
	players := make(map[string]*Player, len(w.players))
	for id, p := range w.players {
		players[id] = clonePlayer(p)
	}
	zombies := make(map[string]*Zombie, len(w.zombies))
	for id, z := range w.zombies {
		zombies[id] = cloneZombie(z)
	}
	projectiles := make(map[string]*Projectile, len(w.projectiles))
	for id, p := range w.projectiles {
		cp := *p
		projectiles[id] = &cp
	}
	grenades := make(map[string]*Grenade, len(w.grenades))
	for id, g := range w.grenades {
		cp := *g
		grenades[id] = &cp
	}
	mines := make(map[string]*Mine, len(w.mines))
	for id, m := range w.mines {
		cp := *m
		mines[id] = &cp
	}
	poisonShots := make(map[string]*PoisonProjectile, len(w.poisonShots))
	for id, p := range w.poisonShots {
		cp := *p
		poisonShots[id] = &cp
	}
	poisonPools := make(map[string]*PoisonPool, len(w.poisonPools))
	for id, p := range w.poisonPools {
		cp := *p
		poisonPools[id] = &cp
	}
	loot := make(map[string]*Loot, len(w.loot))
	for id, item := range w.loot {
		cp := *item
		loot[id] = &cp
	}
	buildings := make(map[string]*Building, len(w.buildings))
	for id, building := range w.buildings {
		buildings[id] = shared.CloneBuilding(building)
	}
	return Snapshot{
		Tick:              w.tick.Load(),
		Time:              w.worldTime,
		MapWidth:          w.cfg.MapWidth,
		MapHeight:         w.cfg.MapHeight,
		Players:           players,
		Zombies:           zombies,
		Projectiles:       projectiles,
		Grenades:          grenades,
		Mines:             mines,
		PoisonProjectiles: poisonShots,
		PoisonPools:       poisonPools,
		Loot:              loot,
		Buildings:         buildings,
	}
}

func (w *World) PlayerExists(playerID string) bool {
	w.mu.RLock()
	defer w.mu.RUnlock()
	return w.players[playerID] != nil
}

func (w *World) drainInputs() {
	for {
		select {
		case input := <-w.inputCh:
			if current, ok := w.inputs[input.PlayerID]; !ok || input.Seq >= current.Seq {
				w.inputs[input.PlayerID] = input
			}
		default:
			return
		}
	}
}

func (w *World) drainCommands() {
	for {
		select {
		case command := <-w.commands:
			result := w.applyCommand(command)
			if command.ResultFunc != nil {
				command.ResultFunc(result)
			}
		default:
			return
		}
	}
}

func (w *World) applyCommand(command Command) CommandResult {
	result := CommandResult{PlayerID: command.PlayerID, CommandID: command.CommandID, Kind: command.Kind, OK: true, ServerTick: w.tick.Load()}
	p := w.players[command.PlayerID]
	if p == nil {
		result.OK = false
		result.Reason = "player_missing"
		return result
	}
	if command.Kind != "respawn" && !p.Alive {
		result.OK = false
		result.Reason = "player_dead"
		return result
	}
	switch command.Kind {
	case "respawn":
		if p.Alive {
			return reject(result, "already_alive")
		}
		pos, floor, building := w.safeRespawn()
		p.Alive = true
		p.Health = 100
		p.Armor = max(p.Armor, 15)
		p.Pos = pos
		p.Floor = floor
		p.InsideBuilding = nilIfEmpty(building)
	case "select_slot":
		slot := asString(command.Payload["slot"])
		if !shared.SlotExists(slot) {
			return reject(result, "invalid_slot")
		}
		p.ActiveSlot = slot
	case "pickup":
		if !w.pickupNearby(p) {
			return reject(result, fallbackNoticeReason(p, "no_item_nearby"))
		}
	case "interact":
		if !w.interact(p) {
			return reject(result, "nothing_to_interact")
		}
	case "reload":
		if !w.startReload(p) {
			return reject(result, "reload_unavailable")
		}
	case "toggle_utility":
		if !w.toggleWeaponUtility(p) {
			return reject(result, "no_utility_module")
		}
	case "throw_grenade":
		if !w.throwGrenade(p) {
			return reject(result, "no_explosive")
		}
	case "equip_armor":
		if !w.equipArmorCommand(p, command.Payload) {
			return reject(result, "invalid_armor")
		}
	case "repair":
		slot := asString(command.Payload["slot"])
		if !w.repairArmor(p, slot) {
			return reject(result, "repair_unavailable")
		}
	case "craft":
		key := asString(command.Payload["key"])
		if !w.craft(p, key) {
			return reject(result, "craft_unavailable")
		}
	case "inventory_action":
		action := command.Payload
		if nested, ok := command.Payload["action"].(map[string]any); ok {
			action = nested
		}
		if !w.applyInventoryAction(p, action) {
			return reject(result, "inventory_action_rejected")
		}
	default:
		return reject(result, "unknown_command")
	}
	return result
}

func (w *World) updatePlayers(dt float64) {
	for id, p := range w.players {
		input := w.inputs[id]
		if !p.Alive {
			continue
		}
		p.Angle = p.Pos.AngleTo(Vec2{X: input.AimX, Y: input.AimY})
		move := Vec2{X: input.MoveX, Y: input.MoveY}.Normalize()
		p.Sneaking = input.Sneak && (move.X != 0 || move.Y != 0)
		p.Sprinting = input.Sprint && !p.Sneaking && (move.X != 0 || move.Y != 0)
		speed := p.Speed
		if p.Sneaking {
			speed *= 0.48
		} else if p.Sprinting {
			speed *= SprintMultiplier
		}
		delta := move.Mul(speed * dt)
		p.Pos = w.moveCircle(p.Pos, delta, PlayerRadius, p.Floor).ClampToMap(w.cfg.MapWidth, w.cfg.MapHeight)
		p.InsideBuilding = nilIfEmpty(shared.PointBuilding(w.buildings, p.Pos))
		if p.InsideBuilding == nil && p.Floor != 0 {
			p.Floor = 0
		}
		p.Noise = 0
		if move.X != 0 || move.Y != 0 {
			if p.Sprinting {
				p.Noise = SprintNoise
			} else if !p.Sneaking {
				p.Noise = WalkNoise
			}
		}
		if input.Shooting {
			p.Noise = maxFloat(p.Noise, ShotNoise)
			w.tryShoot(p)
		}
		w.updatePlayerTimers(p, dt)
		p.UpdatedAt = time.Now()
	}
}

func (w *World) updatePlayerTimers(p *Player, dt float64) {
	for _, weapon := range p.Weapons {
		weapon.Cooldown = maxFloat(0, weapon.Cooldown-dt)
		if weapon.ReloadLeft > 0 {
			weapon.ReloadLeft = maxFloat(0, weapon.ReloadLeft-dt)
			if weapon.ReloadLeft <= 0 {
				w.finishReload(weapon)
			}
		}
	}
	if p.HealingLeft > 0 && p.HealingPool > 0 && p.Health < 100 {
		stacks := max(1, p.HealingStacks)
		healed := math.Min(p.HealingPool, p.HealingRate*dt*float64(stacks))
		p.HealingPool -= healed
		p.HealingLeft = maxFloat(0, p.HealingLeft-dt)
		p.Health = min(100, p.Health+int(math.Ceil(healed)))
		if p.HealingLeft <= 0 || p.HealingPool <= 0 || p.Health >= 100 {
			p.HealingStacks = 0
		}
	}
	if p.NoticeTimer > 0 {
		p.NoticeTimer = maxFloat(0, p.NoticeTimer-dt)
		if p.NoticeTimer <= 0 {
			p.Notice = ""
		}
	}
	if cooldown := w.grenadeCooldowns[p.ID]; cooldown > 0 {
		w.grenadeCooldowns[p.ID] = maxFloat(0, cooldown-dt)
	}
}

func (w *World) tryShoot(p *Player) {
	if quick := p.QuickItems[p.ActiveSlot]; quick != nil {
		spec := w.content.Items[quick.Key]
		if spec.Kind == "grenade" {
			_ = w.throwGrenadeFromQuick(p, p.ActiveSlot)
			return
		}
		if spec.Kind == "mine" {
			_ = w.placeMineFromQuick(p, p.ActiveSlot)
			return
		}
	}
	weapon := p.ActiveWeapon()
	if weapon == nil || weapon.Cooldown > 0 || weapon.ReloadLeft > 0 || weapon.Durability <= 0 {
		return
	}
	if weapon.AmmoInMag <= 0 {
		_ = w.startReload(p)
		return
	}
	spec := w.weaponSpec(weapon.Key)
	weapon.AmmoInMag--
	weapon.Durability = maxFloat(0, weapon.Durability-(0.08+w.rng.Float64()*0.14))
	weapon.Cooldown = 1.0 / w.weaponFireRate(weapon)
	rarity := w.raritySpec(weapon.Rarity)
	damage := max(1, int(math.Round(float64(spec.Damage)*rarity.WeaponDamageMultiplier)))
	for pellet := 0; pellet < max(1, spec.Pellets); pellet++ {
		spread := w.rng.Float64()*w.weaponSpread(weapon)*2 - w.weaponSpread(weapon)
		if spec.Pellets > 1 {
			spread += (float64(pellet) - float64(spec.Pellets-1)*0.5) * w.weaponSpread(weapon) * 0.33
		}
		angle := p.Angle + spread
		dir := Vec2{X: math.Cos(angle), Y: math.Sin(angle)}
		id := w.id("shot")
		w.projectiles[id] = &Projectile{
			ID:        id,
			OwnerID:   p.ID,
			Pos:       p.Pos.Add(dir.Mul(PlayerRadius + 8)),
			Velocity:  dir.Mul(spec.ProjectileSpeed),
			Damage:    damage,
			Life:      0.82,
			Radius:    5,
			Floor:     p.Floor,
			WeaponKey: weapon.Key,
		}
	}
}

func (w *World) updateProjectiles(dt float64) {
	dead := make([]string, 0)
	for id, p := range w.projectiles {
		p.Life -= dt
		old := p.Pos
		p.Pos = p.Pos.Add(p.Velocity.Mul(dt))
		if p.Life <= 0 || p.Pos.X < 0 || p.Pos.Y < 0 || p.Pos.X > w.cfg.MapWidth || p.Pos.Y > w.cfg.MapHeight || w.lineBlocked(old, p.Pos, p.Floor, false) {
			dead = append(dead, id)
			continue
		}
		for _, z := range w.zombies {
			if p.Floor != z.Floor || z.Pos.Distance(p.Pos) > w.zombieSpec(z.Kind).Radius+p.Radius {
				continue
			}
			w.damageZombie(z, p.Damage, p.OwnerID, &p.Pos, true)
			dead = append(dead, id)
			break
		}
	}
	for _, id := range dead {
		delete(w.projectiles, id)
	}
}

func (w *World) updateGrenades(dt float64) {
	dead := make([]string, 0)
	for id, g := range w.grenades {
		g.Timer -= dt
		next := g.Pos.Add(g.Velocity.Mul(dt))
		if !w.lineBlocked(g.Pos, next, g.Floor, false) {
			g.Pos = next.ClampToMap(w.cfg.MapWidth, w.cfg.MapHeight)
		}
		g.Velocity = g.Velocity.Mul(0.88)
		spec := w.grenadeSpec(g.Kind)
		if spec.Contact {
			for _, z := range w.zombies {
				if z.Floor == g.Floor && z.Pos.Distance(g.Pos) <= w.zombieSpec(z.Kind).Radius+g.Radius {
					g.Timer = 0
					break
				}
			}
		}
		if g.Timer <= 0 {
			w.explodeAt(g.Pos, g.Floor, g.OwnerID, spec.BlastRadius, spec.ZombieDamage, spec.ZombieDamageBonus, spec.PlayerDamage, spec.PlayerDamageBonus)
			dead = append(dead, id)
		}
	}
	for _, id := range dead {
		delete(w.grenades, id)
	}
}

func (w *World) updateMines(dt float64) {
	dead := make([]string, 0)
	for id, mine := range w.mines {
		mine.Rotation += dt * 1.6
		owner := w.players[mine.OwnerID]
		if !mine.Armed && (owner == nil || owner.Floor != mine.Floor || owner.Pos.Distance(mine.Pos) > mine.TriggerRadius+PlayerRadius) {
			mine.Armed = true
		}
		if !mine.Armed {
			continue
		}
		triggered := false
		for _, z := range w.zombies {
			if z.Floor == mine.Floor && z.Pos.Distance(mine.Pos) <= mine.TriggerRadius+w.zombieSpec(z.Kind).Radius {
				triggered = true
				break
			}
		}
		for _, p := range w.players {
			if p.Floor == mine.Floor && p.Alive && p.Pos.Distance(mine.Pos) <= mine.TriggerRadius+PlayerRadius {
				triggered = true
				break
			}
		}
		if triggered {
			spec := w.mineSpec(mine.Kind)
			w.explodeAt(mine.Pos, mine.Floor, mine.OwnerID, spec.BlastRadius, spec.ZombieDamage, spec.ZombieDamageBonus, spec.PlayerDamage, spec.PlayerDamageBonus)
			dead = append(dead, id)
		}
	}
	for _, id := range dead {
		delete(w.mines, id)
	}
}

func (w *World) alertZombieFromDamage(z *Zombie, ownerID string, source *Vec2) {
	if p := w.players[ownerID]; p != nil && p.Alive {
		z.Mode = "chase"
		z.TargetPlayerID = p.ID
		z.LastKnown = p.Pos
		z.HasLastKnown = true
		z.HasWaypoint = false
		z.Alertness = 1
		z.SearchTimer = 5
		z.Facing = z.Pos.AngleTo(p.Pos)
		z.Generation++
		z.DecisionDue = w.worldTime
		return
	}
	if source != nil {
		z.Mode = "investigate"
		z.TargetPlayerID = ""
		z.LastKnown = *source
		z.HasLastKnown = true
		z.HasWaypoint = false
		z.SearchTimer = 5
		z.Alertness = 1
		z.Generation++
		z.DecisionDue = w.worldTime
	}
}

func (w *World) updateZombies(dt float64) {
	if w.cfg.Mode == "pvp" {
		return
	}
	for _, z := range w.zombies {
		z.AttackCooldown = maxFloat(0, z.AttackCooldown-dt)
		spec := w.zombieSpec(z.Kind)
		switch z.Mode {
		case "chase":
			target := w.players[z.TargetPlayerID]
			dest := z.LastKnown
			if target != nil && target.Alive && target.Floor == z.Floor {
				dest = target.Pos
				z.LastKnown = target.Pos
				z.HasLastKnown = true
				if z.Pos.Distance(target.Pos) <= ZombieHitRadius+spec.Radius && z.AttackCooldown <= 0 {
					w.damagePlayer(target, spec.Damage)
					z.AttackCooldown = 0.7
				}
			}
			w.moveZombie(z, dest, dt, true)
			if z.HasLastKnown && z.Pos.Distance(z.LastKnown) < 28 && target == nil {
				z.Mode = "search"
				z.SearchTimer = 5
			}
		case "investigate":
			if z.HasLastKnown {
				w.moveZombie(z, z.LastKnown, dt, false)
				if z.Pos.Distance(z.LastKnown) < 34 {
					z.Mode = "search"
					z.SearchTimer = 5
				}
			} else {
				z.Mode = "patrol"
			}
		case "search":
			z.SearchTimer -= dt
			if z.SearchTimer <= 0 {
				z.Mode = "patrol"
				z.TargetPlayerID = ""
				z.HasLastKnown = false
				z.HasWaypoint = false
				z.Alertness = 0
				continue
			}
			if !z.HasWaypoint || z.Pos.Distance(z.Waypoint) < 26 {
				base := z.Pos
				if z.HasLastKnown {
					base = z.LastKnown
				}
				z.Waypoint = w.randomAround(base, 80, 240, z.Floor)
				z.HasWaypoint = true
			}
			w.moveZombie(z, z.Waypoint, dt, false)
		default:
			if z.IdleTimer > 0 {
				z.IdleTimer -= dt
				continue
			}
			if !z.HasWaypoint || z.Pos.Distance(z.Waypoint) < 38 {
				z.Waypoint = w.randomPatrolPos()
				z.HasWaypoint = true
				if w.rng.Float64() < 0.22 {
					z.IdleTimer = 0.4 + w.rng.Float64()*1.4
				}
			}
			w.moveZombie(z, z.Waypoint, dt, false)
		}
	}
}

func (w *World) moveZombie(z *Zombie, target Vec2, dt float64, sprint bool) {
	dir := Vec2{X: target.X - z.Pos.X, Y: target.Y - z.Pos.Y}
	if dir.X == 0 && dir.Y == 0 {
		return
	}
	z.Facing = math.Atan2(dir.Y, dir.X)
	speed := w.zombieSpec(z.Kind).Speed
	if sprint {
		speed *= 1.22
		if z.Kind == "leaper" {
			z.StrafePhase += dt * 2.6
			side := Vec2{X: -math.Sin(z.Facing), Y: math.Cos(z.Facing)}
			dir = dir.Normalize().Add(side.Mul(math.Sin(z.StrafePhase) * 0.42))
		}
	}
	next := w.moveCircle(z.Pos, dir.Normalize().Mul(speed*dt), w.zombieSpec(z.Kind).Radius, z.Floor).ClampToMap(w.cfg.MapWidth, w.cfg.MapHeight)
	if next.Distance(z.Pos) < 0.2 && z.Mode == "patrol" {
		z.Waypoint = w.randomPatrolPos()
		z.HasWaypoint = true
	}
	z.Pos = next
	z.InsideBuilding = nilIfEmpty(shared.PointBuilding(w.buildings, z.Pos))
}

func (w *World) primeMap() {
	w.spawnInitialZombies()
	for _, key := range []string{"smg", "shotgun", "rifle"} {
		w.spawnLoot("weapon", key, 1, "")
	}
	for _, key := range []string{"light", "tactical", "heavy"} {
		w.spawnLoot("armor", key, 1, "")
	}
	for i := 0; i < 16; i++ {
		w.spawnLoot("ammo", w.randomWeaponKey(), 12+w.rng.Intn(24), "")
	}
	for i := 0; i < 42; i++ {
		w.spawnRandomWorldLoot()
	}
	for _, building := range w.buildings {
		for i := 0; i < 8; i++ {
			floor := []int{building.MinFloor, building.MinFloor, 0, 0, 1, 2}[w.rng.Intn(6)]
			pos := Vec2{
				X: building.Bounds.X + 90 + w.rng.Float64()*maxFloat(1, building.Bounds.W-180),
				Y: building.Bounds.Y + 90 + w.rng.Float64()*maxFloat(1, building.Bounds.H-180),
			}
			if w.blockedAt(pos, 16, floor) {
				continue
			}
			table := w.content.HouseLoot
			if floor == building.MinFloor {
				table = w.content.BasementLoot
			}
			key := w.weightedLoot(table)
			amount := 1 + w.rng.Intn(3)
			w.spawnLootAt(pos, "item", key, amount, floor, "")
		}
	}
}

func (w *World) spawnInitialZombies() {
	if w.cfg.Mode == "pvp" {
		return
	}
	for i := 0; i < w.cfg.InitialZombies; i++ {
		w.spawnZombie()
	}
}

func (w *World) spawnZombie() {
	kinds := []string{"walker", "runner", "brute", "leaper"}
	weights := []float64{0.48, 0.24, 0.14, 0.14}
	kind := kinds[w.weightedIndex(weights)]
	spec := w.zombieSpec(kind)
	id := w.id("z")
	w.zombies[id] = &Zombie{
		ID:          id,
		Kind:        kind,
		Pos:         w.randomEdgePos(),
		Health:      spec.Health,
		Armor:       spec.Armor,
		Mode:        "patrol",
		Facing:      w.rng.Float64()*math.Pi*2 - math.Pi,
		Waypoint:    w.randomPatrolPos(),
		HasWaypoint: true,
		DecisionDue: w.rng.Float64(),
		Floor:       0,
	}
}

func (w *World) spawnRandomWorldLoot() {
	key := w.weightedLoot(w.content.WorldLoot)
	w.spawnLoot("item", key, 1+w.rng.Intn(3), "")
}

func (w *World) spawnLoot(kind, payload string, amount int, rarity string) *Loot {
	return w.spawnLootAt(w.randomOpenPos(false), kind, payload, amount, 0, rarity)
}

func (w *World) spawnLootAt(pos Vec2, kind, payload string, amount int, floor int, rarity string) *Loot {
	if rarity == "" {
		rarity = w.lootRarity(kind, payload)
	}
	id := w.id("l")
	item := &Loot{ID: id, Kind: kind, Pos: pos, Payload: payload, Amount: max(1, amount), Floor: floor, Rarity: rarity}
	w.loot[id] = item
	return item
}

func (w *World) randomEdgePos() Vec2 {
	switch w.rng.Intn(4) {
	case 0:
		return Vec2{X: w.rng.Float64() * w.cfg.MapWidth, Y: 40}
	case 1:
		return Vec2{X: w.cfg.MapWidth - 40, Y: w.rng.Float64() * w.cfg.MapHeight}
	case 2:
		return Vec2{X: w.rng.Float64() * w.cfg.MapWidth, Y: w.cfg.MapHeight - 40}
	default:
		return Vec2{X: 40, Y: w.rng.Float64() * w.cfg.MapHeight}
	}
}

func (w *World) randomOpenPos(centered bool) Vec2 {
	for i := 0; i < 500; i++ {
		var pos Vec2
		if centered {
			pos = Vec2{X: w.cfg.MapWidth*0.5 + w.rng.Float64()*720 - 360, Y: w.cfg.MapHeight*0.5 + w.rng.Float64()*600 - 300}
		} else {
			pos = Vec2{X: 160 + w.rng.Float64()*(w.cfg.MapWidth-320), Y: 160 + w.rng.Float64()*(w.cfg.MapHeight-320)}
		}
		if !w.blockedAt(pos, PlayerRadius, 0) {
			return pos
		}
	}
	return Vec2{X: w.cfg.MapWidth * 0.5, Y: w.cfg.MapHeight * 0.5}
}

func (w *World) randomPatrolPos() Vec2 {
	for i := 0; i < 500; i++ {
		pos := w.randomOpenPos(false)
		if !w.nearBuilding(pos, 340) {
			return pos
		}
	}
	return w.randomOpenPos(false)
}

func (w *World) randomAround(base Vec2, minDist, maxDist float64, floor int) Vec2 {
	for i := 0; i < 80; i++ {
		angle := w.rng.Float64() * math.Pi * 2
		dist := minDist + w.rng.Float64()*(maxDist-minDist)
		pos := Vec2{X: base.X + math.Cos(angle)*dist, Y: base.Y + math.Sin(angle)*dist}.ClampToMap(w.cfg.MapWidth, w.cfg.MapHeight)
		if !w.blockedAt(pos, ZombieRadius, floor) {
			return pos
		}
	}
	return base
}

func (w *World) nearBuilding(pos Vec2, margin float64) bool {
	for _, building := range w.buildings {
		if building.Bounds.Inflated(margin).Contains(pos) {
			return true
		}
	}
	return false
}

func (w *World) moveCircle(pos Vec2, delta Vec2, radius float64, floor int) Vec2 {
	return shared.MoveCircleAgainstRects(pos, delta, radius, w.closedWalls(floor))
}

func (w *World) blockedAt(pos Vec2, radius float64, floor int) bool {
	return shared.BlockedAt(pos, radius, w.closedWalls(floor))
}

func (w *World) closedWalls(floor int) []shared.RectState {
	return shared.AllClosedWalls(w.buildings, floor)
}

func (w *World) lineBlocked(start Vec2, end Vec2, floor int, sound bool) bool {
	for _, wall := range w.closedWalls(floor) {
		if shared.SegmentRectIntersects(start, end, wall) {
			if sound && wall.W < 28 && wall.H < 90 {
				continue
			}
			return true
		}
	}
	return false
}

func (w *World) id(prefix string) string {
	return prefix + strconv.FormatInt(w.nextID.Add(1), 10)
}

func clonePlayer(p *Player) *Player {
	cp := *p
	cp.KillsByKind = map[string]int{}
	for k, v := range p.KillsByKind {
		cp.KillsByKind[k] = v
	}
	cp.OwnedArmors = append([]string(nil), p.OwnedArmors...)
	cp.Weapons = map[string]*Weapon{}
	for slot, weapon := range p.Weapons {
		wc := *weapon
		wc.Modules = map[string]any{}
		for k, v := range weapon.Modules {
			wc.Modules[k] = v
		}
		cp.Weapons[slot] = &wc
	}
	cp.Backpack = make([]*shared.InventoryItem, len(p.Backpack))
	for i, item := range p.Backpack {
		if item != nil {
			ic := *item
			cp.Backpack[i] = &ic
		}
	}
	cp.Equipment = map[string]*shared.InventoryItem{}
	for slot, item := range p.Equipment {
		if item != nil {
			ic := *item
			cp.Equipment[slot] = &ic
		} else {
			cp.Equipment[slot] = nil
		}
	}
	cp.QuickItems = map[string]*shared.InventoryItem{}
	for slot, item := range p.QuickItems {
		if item != nil {
			ic := *item
			cp.QuickItems[slot] = &ic
		} else {
			cp.QuickItems[slot] = nil
		}
	}
	return &cp
}

func cloneZombie(z *Zombie) *Zombie {
	cp := *z
	return &cp
}

func cleanName(name string) string {
	if name == "" {
		return "Operator"
	}
	if len(name) > 18 {
		return name[:18]
	}
	return name
}

func reject(result CommandResult, reason string) CommandResult {
	result.OK = false
	result.Reason = reason
	return result
}

func nilIfEmpty(value string) any {
	if value == "" {
		return nil
	}
	return value
}

func fallbackNoticeReason(p *Player, fallback string) string {
	if p.Notice == "notice.backpack_full" {
		return "backpack_full"
	}
	return fallback
}

func clamp(value, low, high float64) float64 {
	return math.Max(low, math.Min(high, value))
}

func maxFloat(a, b float64) float64 {
	if a > b {
		return a
	}
	return b
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
