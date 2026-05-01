package shared

import "math"

const SnapshotSchema = "compact-v1"

func CompactSnapshot(snapshot WorldSnapshot, localPlayerID string, interestRadius float64) map[string]any {
	local := snapshot.Players[localPlayerID]
	compact := map[string]any{
		"v":  1,
		"t":  Round(snapshot.Time, 3),
		"mw": int(snapshot.MapWidth),
		"mh": int(snapshot.MapHeight),
		"p":  []any{},
		"z":  []any{},
		"s":  []any{},
		"g":  []any{},
		"m":  []any{},
		"pp": []any{},
		"pl": []any{},
		"l":  []any{},
		"b":  buildingsPayload(snapshot.Buildings),
	}
	if local != nil {
		compact["lp"] = PlayerDict(local)
	}
	compact["p"] = filterPackPlayers(snapshot.Players, local, localPlayerID, interestRadius)
	compact["z"] = filterPackZombies(snapshot.Zombies, local, interestRadius)
	compact["s"] = filterPackProjectiles(snapshot.Projectiles, local, interestRadius)
	compact["g"] = filterPackGrenades(snapshot.Grenades, local, interestRadius)
	compact["m"] = filterPackMines(snapshot.Mines, local, interestRadius)
	compact["pp"] = filterPackPoisonProjectiles(snapshot.PoisonProjectiles, local, interestRadius)
	compact["pl"] = filterPackPoisonPools(snapshot.PoisonPools, local, interestRadius)
	compact["l"] = filterPackLoot(snapshot.Loot, local, interestRadius)
	return compact
}

func PlayerDict(p *PlayerState) map[string]any {
	weapons := map[string]any{}
	for slot, weapon := range p.Weapons {
		weapons[slot] = WeaponDict(weapon)
	}
	backpack := make([]any, len(p.Backpack))
	for i, item := range p.Backpack {
		if item != nil {
			backpack[i] = item.ToMap()
		}
	}
	equipment := map[string]any{"head": nil, "torso": nil, "legs": nil, "arms": nil}
	for slot, item := range p.Equipment {
		if item != nil {
			equipment[slot] = item.ToMap()
		} else {
			equipment[slot] = nil
		}
	}
	quickItems := map[string]any{}
	for slot, item := range p.QuickItems {
		if item != nil {
			quickItems[slot] = item.ToMap()
		} else {
			quickItems[slot] = nil
		}
	}
	return map[string]any{
		"id":                 p.ID,
		"name":               p.Name,
		"pos":                p.Pos.ToMap(),
		"angle":              Round(p.Angle, 4),
		"health":             p.Health,
		"armor":              p.Armor,
		"armor_key":          p.ArmorKey,
		"speed":              p.Speed,
		"active_slot":        p.ActiveSlot,
		"alive":              p.Alive,
		"score":              p.Score,
		"kills_by_kind":      p.KillsByKind,
		"medkits":            p.Medkits,
		"owned_armors":       p.OwnedArmors,
		"noise":              Round(p.Noise, 3),
		"sprinting":          p.Sprinting,
		"floor":              p.Floor,
		"inside_building":    p.InsideBuilding,
		"sneaking":           p.Sneaking,
		"backpack":           backpack,
		"equipment":          equipment,
		"quick_items":        quickItems,
		"healing_left":       Round(p.HealingLeft, 3),
		"healing_rate":       Round(p.HealingRate, 3),
		"healing_pool":       Round(p.HealingPool, 3),
		"healing_stacks":     p.HealingStacks,
		"poison_left":        Round(p.PoisonLeft, 3),
		"poison_tick":        Round(p.PoisonTick, 3),
		"poison_damage":      p.PoisonDamage,
		"melee_cooldown":     Round(p.MeleeCooldown, 3),
		"notice":             p.Notice,
		"notice_timer":       Round(p.NoticeTimer, 3),
		"ping_ms":            p.PingMS,
		"connection_quality": p.ConnectionQuality,
		"weapons":            weapons,
	}
}

func WeaponDict(w *WeaponRuntime) map[string]any {
	if w == nil {
		return nil
	}
	return w.ToMap()
}

func PackPlayer(p *PlayerState) []any {
	return []any{
		p.ID,
		p.Name,
		q(p.Pos.X, 10),
		q(p.Pos.Y, 10),
		q(p.Angle, 1000),
		p.Health,
		p.Armor,
		p.ArmorKey,
		p.ActiveSlot,
		boolInt(p.Alive),
		p.Score,
		p.KillsByKind,
		q(p.Noise, 10),
		boolInt(p.Sprinting),
		p.Floor,
		nilIfEmptyAny(p.InsideBuilding),
		boolInt(p.Sneaking),
		q(p.PoisonLeft, 1000),
		WeaponDict(p.ActiveWeapon()),
		p.PingMS,
		p.ConnectionQuality,
	}
}

func PackZombie(z *ZombieState) []any {
	return []any{
		z.ID,
		z.Kind,
		q(z.Pos.X, 10),
		q(z.Pos.Y, 10),
		z.Health,
		z.Armor,
		z.Mode,
		q(z.Facing, 1000),
		z.Floor,
		nilIfEmpty(z.TargetPlayerID),
		q(z.Alertness, 1000),
	}
}

func PackProjectile(p *ProjectileState) []any {
	return []any{
		p.ID,
		p.OwnerID,
		q(p.Pos.X, 10),
		q(p.Pos.Y, 10),
		q(p.Velocity.X, 10),
		q(p.Velocity.Y, 10),
		p.Damage,
		q(p.Life, 1000),
		q(p.Radius, 10),
		p.Floor,
		p.WeaponKey,
	}
}

func PackGrenade(g *GrenadeState) []any {
	return []any{
		g.ID,
		g.OwnerID,
		q(g.Pos.X, 10),
		q(g.Pos.Y, 10),
		q(g.Velocity.X, 10),
		q(g.Velocity.Y, 10),
		0,
		q(g.Timer, 1000),
		q(g.Radius, 10),
		g.Floor,
		g.Kind,
	}
}

func PackMine(m *MineState) []any {
	return []any{
		m.ID,
		m.OwnerID,
		m.Kind,
		q(m.Pos.X, 10),
		q(m.Pos.Y, 10),
		m.Floor,
		boolInt(m.Armed),
		q(m.TriggerRadius, 10),
		q(m.BlastRadius, 10),
		q(m.Rotation, 1000),
	}
}

func PackPoisonProjectile(p *PoisonProjectileState) []any {
	return []any{
		p.ID,
		p.OwnerID,
		q(p.Pos.X, 10),
		q(p.Pos.Y, 10),
		q(p.Velocity.X, 10),
		q(p.Velocity.Y, 10),
		q(p.Target.X, 10),
		q(p.Target.Y, 10),
		p.Floor,
		q(p.Radius, 10),
		q(p.Life, 1000),
	}
}

func PackPoisonPool(p *PoisonPoolState) []any {
	return []any{
		p.ID,
		q(p.Pos.X, 10),
		q(p.Pos.Y, 10),
		p.Floor,
		q(p.Timer, 1000),
		q(p.Radius, 10),
	}
}

func PackLoot(l *LootState) []any {
	return []any{
		l.ID,
		l.Kind,
		q(l.Pos.X, 10),
		q(l.Pos.Y, 10),
		l.Payload,
		l.Amount,
		l.Floor,
		l.Rarity,
	}
}

func filterPackPlayers(players map[string]*PlayerState, local *PlayerState, localID string, radius float64) []any {
	rows := make([]any, 0, len(players))
	for id, player := range players {
		if id == localID {
			continue
		}
		if !visibleToLocal(local, player.Pos, player.Floor, radius) {
			continue
		}
		rows = append(rows, PackPlayer(player))
	}
	return rows
}

func filterPackZombies(zombies map[string]*ZombieState, local *PlayerState, radius float64) []any {
	rows := make([]any, 0, len(zombies))
	for _, zombie := range zombies {
		if !visibleToLocal(local, zombie.Pos, zombie.Floor, radius) {
			continue
		}
		rows = append(rows, PackZombie(zombie))
	}
	return rows
}

func filterPackProjectiles(projectiles map[string]*ProjectileState, local *PlayerState, radius float64) []any {
	rows := make([]any, 0, len(projectiles))
	for _, projectile := range projectiles {
		if !visibleToLocal(local, projectile.Pos, projectile.Floor, radius) {
			continue
		}
		rows = append(rows, PackProjectile(projectile))
	}
	return rows
}

func filterPackGrenades(grenades map[string]*GrenadeState, local *PlayerState, radius float64) []any {
	rows := make([]any, 0, len(grenades))
	for _, grenade := range grenades {
		if !visibleToLocal(local, grenade.Pos, grenade.Floor, radius) {
			continue
		}
		rows = append(rows, PackGrenade(grenade))
	}
	return rows
}

func filterPackMines(mines map[string]*MineState, local *PlayerState, radius float64) []any {
	rows := make([]any, 0, len(mines))
	for _, mine := range mines {
		if !visibleToLocal(local, mine.Pos, mine.Floor, radius) {
			continue
		}
		rows = append(rows, PackMine(mine))
	}
	return rows
}

func filterPackPoisonProjectiles(projectiles map[string]*PoisonProjectileState, local *PlayerState, radius float64) []any {
	rows := make([]any, 0, len(projectiles))
	for _, projectile := range projectiles {
		if !visibleToLocal(local, projectile.Pos, projectile.Floor, radius) {
			continue
		}
		rows = append(rows, PackPoisonProjectile(projectile))
	}
	return rows
}

func filterPackPoisonPools(pools map[string]*PoisonPoolState, local *PlayerState, radius float64) []any {
	rows := make([]any, 0, len(pools))
	for _, pool := range pools {
		if !visibleToLocal(local, pool.Pos, pool.Floor, radius) {
			continue
		}
		rows = append(rows, PackPoisonPool(pool))
	}
	return rows
}

func filterPackLoot(loot map[string]*LootState, local *PlayerState, radius float64) []any {
	rows := make([]any, 0, len(loot))
	for _, item := range loot {
		if !visibleToLocal(local, item.Pos, item.Floor, radius) {
			continue
		}
		rows = append(rows, PackLoot(item))
	}
	return rows
}

func visibleToLocal(local *PlayerState, pos Vec2, floor int, radius float64) bool {
	if local == nil {
		return true
	}
	if local.Floor != floor {
		return false
	}
	return local.Pos.Distance(pos) <= radius
}

func buildingsPayload(buildings map[string]*BuildingState) map[string]any {
	out := make(map[string]any, len(buildings))
	for id, building := range buildings {
		out[id] = building.ToMap()
	}
	return out
}

func q(value float64, scale float64) int {
	return int(math.Round(value * scale))
}

func boolInt(value bool) int {
	if value {
		return 1
	}
	return 0
}

func nilIfEmpty(value string) any {
	if value == "" {
		return nil
	}
	return value
}

func nilIfEmptyAny(value any) any {
	if value == nil {
		return nil
	}
	if text, ok := value.(string); ok && text == "" {
		return nil
	}
	return value
}
