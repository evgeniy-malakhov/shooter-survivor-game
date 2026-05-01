package game

import (
	"math"

	"neonoutbreak/server_go/shared"
)

func (w *World) pickupNearby(player *Player) bool {
	loot := w.nearestLoot(player)
	if loot == nil {
		return false
	}
	ok := false
	switch loot.Kind {
	case "weapon":
		if spec, exists := w.content.Weapons[loot.Payload]; exists {
			if current := player.Weapons[spec.Slot]; current != nil {
				current.ReserveAmmo += spec.MagazineSize
				if w.rarityRank(loot.Rarity) > w.rarityRank(current.Rarity) {
					current.Rarity = loot.Rarity
					current.Durability = maxFloat(current.Durability, 100)
				}
				ok = true
			} else if slot := w.freeQuickSlot(player, spec.Slot); slot != "" {
				player.Weapons[slot] = shared.NewWeaponRuntime(spec, spec.MagazineSize*2, loot.Rarity)
				player.ActiveSlot = slot
				ok = true
			} else {
				ok = w.addWeaponToBackpack(player, spec.Key, loot.Rarity, 100)
			}
			if ok {
				_ = w.addItem(player, "ammo_pack", 1, "common")
			}
		}
	case "ammo":
		ok = w.addItem(player, "ammo_pack", max(1, loot.Amount/12), "common")
		for _, weapon := range player.Weapons {
			if weapon != nil && weapon.Key == loot.Payload {
				weapon.ReserveAmmo += loot.Amount
				break
			}
		}
	case "armor":
		key := loot.Payload + "_torso"
		if _, exists := w.content.Items[key]; !exists {
			key = "light_torso"
		}
		ok = w.addItem(player, key, 1, loot.Rarity)
	case "medkit":
		ok = w.addItem(player, "medicine", loot.Amount, "common")
		if ok {
			player.Medkits += loot.Amount
		}
	default:
		if loot.Payload != "" {
			ok = w.addItem(player, loot.Payload, loot.Amount, loot.Rarity)
		}
	}
	if !ok {
		w.setNotice(player, "notice.backpack_full", 2.2)
		return false
	}
	delete(w.loot, loot.ID)
	return true
}

func (w *World) nearestLoot(player *Player) *Loot {
	var best *Loot
	bestDistance := shared.PickupRadius
	for _, item := range w.loot {
		if item.Floor != player.Floor {
			continue
		}
		distance := item.Pos.Distance(player.Pos)
		if distance <= bestDistance {
			best = item
			bestDistance = distance
		}
	}
	return best
}

func (w *World) interact(player *Player) bool {
	floor := player.Floor
	if door := shared.NearestDoor(w.buildings, player.Pos, shared.InteractRadius, &floor); door != nil {
		door.Open = !door.Open
		return true
	}
	building := shared.NearestStairs(w.buildings, player.Pos, shared.InteractRadius)
	if building != nil && building.Bounds.Contains(player.Pos) {
		player.Floor++
		if player.Floor > building.MaxFloor() {
			player.Floor = building.MinFloor
		}
		player.InsideBuilding = building.ID
		return true
	}
	return false
}

func (w *World) startReload(player *Player) bool {
	weapon := player.ActiveWeapon()
	if weapon == nil || weapon.ReserveAmmo <= 0 || weapon.AmmoInMag >= w.weaponMagazineSize(weapon) || weapon.ReloadLeft > 0 {
		return false
	}
	weapon.ReloadLeft = w.weaponSpec(weapon.Key).ReloadTime
	return true
}

func (w *World) finishReload(weapon *Weapon) {
	if weapon == nil {
		return
	}
	needed := w.weaponMagazineSize(weapon) - weapon.AmmoInMag
	loaded := min(needed, weapon.ReserveAmmo)
	weapon.AmmoInMag += loaded
	weapon.ReserveAmmo -= loaded
}

func (w *World) weaponMagazineSize(weapon *Weapon) int {
	spec := w.weaponSpec(weapon.Key)
	multiplier := 1.0
	if moduleKey := asString(weapon.Modules["magazine"]); moduleKey != "" {
		if module, ok := w.content.WeaponModules[moduleKey]; ok {
			multiplier = module.MagazineMultiplier
		}
	}
	return max(spec.MagazineSize, int(math.Ceil(float64(spec.MagazineSize)*multiplier)))
}

func (w *World) weaponSpread(weapon *Weapon) float64 {
	spread := w.weaponSpec(weapon.Key).Spread
	moduleKey := asString(weapon.Modules["utility"])
	module, ok := w.content.WeaponModules[moduleKey]
	if !ok {
		return spread
	}
	if moduleKey == "laser_module" && weapon.UtilityOn {
		spread *= module.SpreadMultiplier
	} else if moduleKey == "silencer" || moduleKey == "compensator" {
		spread *= module.SpreadMultiplier
	}
	return spread
}

func (w *World) weaponFireRate(weapon *Weapon) float64 {
	rate := w.weaponSpec(weapon.Key).FireRate
	moduleKey := asString(weapon.Modules["utility"])
	module, ok := w.content.WeaponModules[moduleKey]
	if ok && moduleKey == "compensator" {
		rate *= 1 + maxFloat(0, module.FireRateBonus+module.FireRateRarityStep*float64(w.rarityRank(weapon.Rarity)))
	}
	return maxFloat(0.1, rate)
}

func (w *World) toggleWeaponUtility(player *Player) bool {
	weapon := player.ActiveWeapon()
	if weapon == nil {
		return false
	}
	moduleKey := asString(weapon.Modules["utility"])
	if moduleKey != "laser_module" && moduleKey != "flashlight_module" {
		return false
	}
	weapon.UtilityOn = !weapon.UtilityOn
	return true
}

func (w *World) applyInventoryAction(player *Player, action map[string]any) bool {
	switch asString(action["type"]) {
	case "move":
		return w.moveInventoryItem(player, action)
	case "quick_swap":
		a := asString(action["a"])
		b := asString(action["b"])
		if !shared.SlotExists(a) || !shared.SlotExists(b) {
			return false
		}
		player.Weapons[a], player.Weapons[b] = player.Weapons[b], player.Weapons[a]
		player.QuickItems[a], player.QuickItems[b] = player.QuickItems[b], player.QuickItems[a]
		if player.Weapons[a] == nil {
			delete(player.Weapons, a)
		}
		if player.Weapons[b] == nil {
			delete(player.Weapons, b)
		}
		return true
	case "drop":
		return w.dropInventoryItem(player, action)
	case "use":
		index := asInt(action["index"], -1)
		if index < 0 || index >= len(player.Backpack) || player.Backpack[index] == nil {
			return false
		}
		if !w.useItem(player, player.Backpack[index]) {
			return false
		}
		player.Backpack[index].Amount--
		if player.Backpack[index].Amount <= 0 {
			player.Backpack[index] = nil
		}
		return true
	case "repair_drag":
		return w.repairWithKit(player, action)
	case "unequip_module":
		slot := asString(action["slot"])
		moduleSlot := asString(action["module_slot"])
		item := w.takeItem(player, "weapon_module", -1, slot, moduleSlot)
		if item == nil {
			return false
		}
		if !w.addItem(player, item.Key, item.Amount, item.Rarity) {
			_ = w.placeItem(player, "weapon_module", -1, slot, item, moduleSlot)
			return false
		}
		return true
	default:
		return false
	}
}

func (w *World) moveInventoryItem(player *Player, action map[string]any) bool {
	src := asStringDefault(action["src"], "backpack")
	dst := asStringDefault(action["dst"], "backpack")
	srcIndex := asInt(action["src_index"], -1)
	dstIndex := asInt(action["dst_index"], -1)
	srcSlot := asString(action["src_slot"])
	dstSlot := asString(action["dst_slot"])
	srcModule := asString(action["src_module"])
	dstModule := asString(action["dst_module"])
	item := w.takeItem(player, src, srcIndex, srcSlot, srcModule)
	if item == nil {
		return false
	}
	displaced := w.placeItem(player, dst, dstIndex, dstSlot, item, dstModule)
	if displaced != nil {
		_ = w.placeItem(player, src, srcIndex, srcSlot, displaced, srcModule)
	}
	w.recalculateArmor(player)
	return true
}

func (w *World) takeItem(player *Player, source string, index int, slot string, moduleSlot string) *shared.InventoryItem {
	switch source {
	case "backpack":
		if index < 0 || index >= len(player.Backpack) {
			return nil
		}
		item := player.Backpack[index]
		player.Backpack[index] = nil
		return item
	case "weapon_slot":
		weapon := player.Weapons[slot]
		if weapon == nil {
			return nil
		}
		delete(player.Weapons, slot)
		if player.ActiveSlot == slot {
			player.ActiveSlot = firstOccupiedSlot(player)
		}
		return &shared.InventoryItem{ID: w.id("it"), Key: weapon.Key, Amount: 1, Durability: weapon.Durability, Rarity: weapon.Rarity}
	case "equipment":
		item := player.Equipment[slot]
		player.Equipment[slot] = nil
		return item
	case "quick_item":
		item := player.QuickItems[slot]
		player.QuickItems[slot] = nil
		return item
	case "weapon_module":
		weapon := player.Weapons[slot]
		if weapon == nil {
			return nil
		}
		moduleKey := asString(weapon.Modules[moduleSlot])
		if moduleKey == "" {
			return nil
		}
		weapon.Modules[moduleSlot] = nil
		if moduleSlot == "utility" {
			weapon.UtilityOn = false
		}
		if moduleSlot == "magazine" {
			weapon.AmmoInMag = min(weapon.AmmoInMag, w.weaponMagazineSize(weapon))
		}
		return &shared.InventoryItem{ID: w.id("it"), Key: moduleKey, Amount: 1, Durability: 100, Rarity: "common"}
	default:
		return nil
	}
}

func (w *World) placeItem(player *Player, destination string, index int, slot string, item *shared.InventoryItem, moduleSlot string) *shared.InventoryItem {
	if item == nil {
		return nil
	}
	switch destination {
	case "weapon_module":
		weapon := player.Weapons[slot]
		module, ok := w.content.WeaponModules[item.Key]
		if weapon == nil || !ok || module.Slot != moduleSlot {
			return item
		}
		displacedKey := asString(weapon.Modules[moduleSlot])
		weapon.Modules[moduleSlot] = item.Key
		if moduleSlot == "utility" {
			weapon.UtilityOn = false
		}
		if moduleSlot == "magazine" {
			weapon.AmmoInMag = min(weapon.AmmoInMag, w.weaponMagazineSize(weapon))
		}
		if displacedKey != "" {
			return &shared.InventoryItem{ID: w.id("it"), Key: displacedKey, Amount: 1, Durability: 100, Rarity: "common"}
		}
		return nil
	case "weapon_slot":
		if !shared.SlotExists(slot) || player.Weapons[slot] != nil || player.QuickItems[slot] != nil {
			return item
		}
		if spec, ok := w.content.Weapons[item.Key]; ok {
			player.Weapons[slot] = shared.NewWeaponRuntime(spec, spec.MagazineSize*2, item.Rarity)
			player.Weapons[slot].Durability = item.Durability
			player.ActiveSlot = slot
			return nil
		}
		if spec := w.content.Items[item.Key]; spec.Kind == "grenade" || spec.Kind == "mine" {
			player.QuickItems[slot] = item
			return nil
		}
		return item
	case "equipment":
		spec := w.content.Items[item.Key]
		if spec.EquipmentSlot != slot {
			return item
		}
		displaced := player.Equipment[slot]
		player.Equipment[slot] = item
		return displaced
	case "quick_item":
		spec := w.content.Items[item.Key]
		if !shared.SlotExists(slot) || (spec.Kind != "grenade" && spec.Kind != "mine") {
			return item
		}
		displaced := player.QuickItems[slot]
		player.QuickItems[slot] = item
		return displaced
	case "backpack":
		if index < 0 || index >= len(player.Backpack) {
			return item
		}
		displaced := player.Backpack[index]
		player.Backpack[index] = item
		return displaced
	default:
		return item
	}
}

func (w *World) dropInventoryItem(player *Player, action map[string]any) bool {
	source := asStringDefault(action["source"], "backpack")
	index := asInt(action["index"], -1)
	slot := asString(action["slot"])
	moduleSlot := asString(action["module_slot"])
	if source == "weapon_slot" {
		weapon := player.Weapons[slot]
		if weapon == nil {
			return false
		}
		delete(player.Weapons, slot)
		w.spawnLootAt(player.Pos, "weapon", weapon.Key, 1, player.Floor, weapon.Rarity)
		if player.ActiveSlot == slot {
			player.ActiveSlot = firstOccupiedSlot(player)
		}
		return true
	}
	item := w.takeItem(player, source, index, slot, moduleSlot)
	if item == nil {
		return false
	}
	w.spawnLootAt(player.Pos, "item", item.Key, item.Amount, player.Floor, item.Rarity)
	w.recalculateArmor(player)
	return true
}

func (w *World) useItem(player *Player, item *shared.InventoryItem) bool {
	spec := w.content.Items[item.Key]
	if (spec.Kind == "food" || spec.Kind == "medical") && spec.HealTotal > 0 && player.Health < 100 {
		player.HealingPool += float64(spec.HealTotal)
		player.HealingLeft = maxFloat(player.HealingLeft, maxFloat(0.1, spec.HealSeconds))
		player.HealingRate = float64(spec.HealTotal) / maxFloat(0.1, spec.HealSeconds)
		player.HealingStacks = max(1, player.HealingStacks+1)
		return true
	}
	if spec.Kind == "ammo" {
		for _, weapon := range player.Weapons {
			if weapon != nil {
				weapon.ReserveAmmo += 12 * item.Amount
			}
		}
		return true
	}
	return false
}

func (w *World) repairWithKit(player *Player, action map[string]any) bool {
	kitIndex := asInt(action["kit_index"], -1)
	if kitIndex < 0 || kitIndex >= len(player.Backpack) || player.Backpack[kitIndex] == nil || player.Backpack[kitIndex].Key != "repair_kit" {
		return false
	}
	targetSource := asString(action["target_source"])
	targetIndex := asInt(action["target_index"], -1)
	targetSlot := asString(action["target_slot"])
	var target *shared.InventoryItem
	if targetSource == "backpack" && targetIndex >= 0 && targetIndex < len(player.Backpack) {
		target = player.Backpack[targetIndex]
	} else if targetSource == "equipment" {
		target = player.Equipment[targetSlot]
	} else if targetSource == "quick_item" {
		target = player.QuickItems[targetSlot]
	} else if targetSource == "weapon_slot" {
		weapon := player.Weapons[targetSlot]
		if weapon == nil {
			return false
		}
		weapon.Durability = 100
		w.consumeBackpackIndex(player, kitIndex, 1)
		return true
	}
	if target == nil || target.Durability >= 100 {
		return false
	}
	target.Durability = 100
	w.consumeBackpackIndex(player, kitIndex, 1)
	return true
}

func (w *World) craft(player *Player, recipeKey string) bool {
	if shared.NearestProp(w.buildings, player.Pos, shared.InteractRadius, "work_bench", player.Floor) == nil {
		return false
	}
	recipe, ok := w.content.Recipes[recipeKey]
	if !ok {
		return false
	}
	for key, amount := range recipe.Requires {
		if w.countItem(player, key) < amount {
			return false
		}
	}
	rarity := "common"
	if spec, ok := w.content.Items[recipe.ResultKey]; ok && (spec.Kind == "armor" || spec.Kind == "weapon_module" || spec.Kind == "grenade" || spec.Kind == "mine") {
		rarity = w.rollRarity()
	}
	if !w.canAddItem(player, recipe.ResultKey, recipe.ResultQty, rarity) {
		w.setNotice(player, "notice.backpack_full", 2.2)
		return false
	}
	for key, amount := range recipe.Requires {
		_ = w.removeItems(player, key, amount)
	}
	return w.addItem(player, recipe.ResultKey, recipe.ResultQty, rarity)
}

func (w *World) repairArmor(player *Player, slot string) bool {
	if shared.NearestProp(w.buildings, player.Pos, shared.InteractRadius, "repair_table", player.Floor) == nil {
		return false
	}
	item := player.Equipment[slot]
	if item == nil || !w.removeItems(player, "repair_kit", 1) {
		return false
	}
	item.Durability = 100
	w.recalculateArmor(player)
	return true
}

func (w *World) equipArmorCommand(player *Player, payload map[string]any) bool {
	armorKey := asString(payload["armor_key"])
	if armorKey == "" {
		return false
	}
	if armor, ok := w.content.Armors[armorKey]; ok {
		player.ArmorKey = armorKey
		player.Armor = max(player.Armor, armor.ArmorPoints)
		return true
	}
	return false
}

func (w *World) addItem(player *Player, key string, amount int, rarity string) bool {
	spec, ok := w.content.Items[key]
	if !ok {
		return false
	}
	if rarity == "" {
		rarity = "common"
	}
	remaining := max(1, amount)
	for _, item := range player.Backpack {
		if item != nil && item.Key == key && item.Rarity == rarity && item.Amount < spec.StackSize {
			add := min(remaining, spec.StackSize-item.Amount)
			item.Amount += add
			remaining -= add
			if remaining <= 0 {
				return true
			}
		}
	}
	for index, item := range player.Backpack {
		if item == nil {
			add := min(remaining, spec.StackSize)
			player.Backpack[index] = &shared.InventoryItem{ID: w.id("it"), Key: key, Amount: add, Durability: 100, Rarity: rarity}
			remaining -= add
			if remaining <= 0 {
				return true
			}
		}
	}
	return false
}

func (w *World) canAddItem(player *Player, key string, amount int, rarity string) bool {
	spec, ok := w.content.Items[key]
	if !ok {
		return false
	}
	capacity := 0
	for _, item := range player.Backpack {
		if item == nil {
			capacity += spec.StackSize
		} else if item.Key == key && item.Rarity == rarity {
			capacity += max(0, spec.StackSize-item.Amount)
		}
		if capacity >= amount {
			return true
		}
	}
	return false
}

func (w *World) addWeaponToBackpack(player *Player, key string, rarity string, durability float64) bool {
	if _, ok := w.content.Weapons[key]; !ok {
		return false
	}
	for index, item := range player.Backpack {
		if item == nil {
			player.Backpack[index] = &shared.InventoryItem{ID: w.id("it"), Key: key, Amount: 1, Durability: durability, Rarity: rarity}
			return true
		}
	}
	return false
}

func (w *World) countItem(player *Player, key string) int {
	total := 0
	for _, item := range player.Backpack {
		if item != nil && item.Key == key {
			total += item.Amount
		}
	}
	return total
}

func (w *World) removeItems(player *Player, key string, amount int) bool {
	if w.countItem(player, key) < amount {
		return false
	}
	remaining := amount
	for index, item := range player.Backpack {
		if item == nil || item.Key != key {
			continue
		}
		take := min(remaining, item.Amount)
		item.Amount -= take
		remaining -= take
		if item.Amount <= 0 {
			player.Backpack[index] = nil
		}
		if remaining <= 0 {
			return true
		}
	}
	return true
}

func (w *World) consumeBackpackIndex(player *Player, index int, amount int) {
	item := player.Backpack[index]
	if item == nil {
		return
	}
	item.Amount -= amount
	if item.Amount <= 0 {
		player.Backpack[index] = nil
	}
}

func (w *World) freeQuickSlot(player *Player, preferred string) string {
	if preferred != "" && shared.SlotExists(preferred) && player.Weapons[preferred] == nil && player.QuickItems[preferred] == nil {
		return preferred
	}
	for _, slot := range shared.Slots {
		if player.Weapons[slot] == nil && player.QuickItems[slot] == nil {
			return slot
		}
	}
	return ""
}

func firstOccupiedSlot(player *Player) string {
	for _, slot := range shared.Slots {
		if player.Weapons[slot] != nil || player.QuickItems[slot] != nil {
			return slot
		}
	}
	return "1"
}

func (w *World) recalculateArmor(player *Player) {
	bestKey := "none"
	bestPoints := 0
	for _, item := range player.Equipment {
		points := w.effectiveArmorPoints(item)
		if points > bestPoints {
			bestPoints = points
			bestKey = w.content.Items[item.Key].ArmorKey
		}
	}
	player.ArmorKey = bestKey
	if bestKey == "none" {
		player.Armor = 0
	} else {
		player.Armor = min(bestPoints, max(player.Armor, int(float64(bestPoints)*0.65)))
	}
}

func (w *World) effectiveArmorPoints(item *shared.InventoryItem) int {
	if item == nil || item.Durability <= 0 {
		return 0
	}
	itemSpec := w.content.Items[item.Key]
	if itemSpec.ArmorKey == "" {
		return 0
	}
	armor := w.content.Armors[itemSpec.ArmorKey]
	rarity := w.raritySpec(item.Rarity)
	return max(0, int(math.Round(float64(armor.ArmorPoints)*rarity.ArmorPointsMultiplier)))
}

func (w *World) throwGrenade(player *Player) bool {
	if w.grenadeCooldowns[player.ID] > 0 {
		return false
	}
	if quick := player.QuickItems[player.ActiveSlot]; quick != nil {
		spec := w.content.Items[quick.Key]
		if spec.Kind == "grenade" {
			return w.throwGrenadeFromQuick(player, player.ActiveSlot)
		}
		if spec.Kind == "mine" {
			return w.placeMineFromQuick(player, player.ActiveSlot)
		}
	}
	for _, key := range []string{"grenade", "contact_grenade", "heavy_grenade"} {
		if w.removeItems(player, key, 1) {
			w.spawnGrenade(player, key)
			return true
		}
	}
	return false
}

func (w *World) throwGrenadeFromQuick(player *Player, slot string) bool {
	if w.grenadeCooldowns[player.ID] > 0 {
		return false
	}
	item := player.QuickItems[slot]
	if item == nil || w.content.Items[item.Key].Kind != "grenade" {
		return false
	}
	key := item.Key
	item.Amount--
	if item.Amount <= 0 {
		player.QuickItems[slot] = nil
	}
	w.spawnGrenade(player, key)
	return true
}

func (w *World) spawnGrenade(player *Player, key string) {
	spec := w.grenadeSpec(key)
	dir := Vec2{X: math.Cos(player.Angle), Y: math.Sin(player.Angle)}
	id := w.id("g")
	w.grenades[id] = &Grenade{
		ID:       id,
		OwnerID:  player.ID,
		Pos:      player.Pos.Add(dir.Mul(PlayerRadius + 12)),
		Velocity: dir.Mul(spec.ThrowDistance),
		Timer:    spec.Timer,
		Floor:    player.Floor,
		Radius:   10,
		Kind:     key,
	}
	w.grenadeCooldowns[player.ID] = 0.6
}

func (w *World) placeMineFromQuick(player *Player, slot string) bool {
	if w.grenadeCooldowns[player.ID] > 0 {
		return false
	}
	item := player.QuickItems[slot]
	if item == nil || w.content.Items[item.Key].Kind != "mine" {
		return false
	}
	spec := w.mineSpec(item.Key)
	dir := Vec2{X: math.Cos(player.Angle), Y: math.Sin(player.Angle)}
	pos := player.Pos.Add(dir.Mul(PlayerRadius+20)).ClampToMap(w.cfg.MapWidth, w.cfg.MapHeight)
	if w.blockedAt(pos, 12, player.Floor) {
		pos = player.Pos
	}
	id := w.id("m")
	w.mines[id] = &Mine{ID: id, OwnerID: player.ID, Kind: item.Key, Pos: pos, Floor: player.Floor, TriggerRadius: spec.TriggerRadius, BlastRadius: spec.BlastRadius}
	item.Amount--
	if item.Amount <= 0 {
		player.QuickItems[slot] = nil
	}
	w.grenadeCooldowns[player.ID] = 0.45
	return true
}

func (w *World) explodeAt(pos Vec2, floor int, ownerID string, blastRadius float64, zombieDamage int, zombieBonus int, playerDamage int, playerBonus int) {
	for _, zombie := range w.zombies {
		if zombie.Floor != floor {
			continue
		}
		distance := zombie.Pos.Distance(pos)
		if distance <= blastRadius && !w.lineBlocked(pos, zombie.Pos, floor, false) {
			damage := int(float64(zombieDamage)*(1-distance/blastRadius)) + zombieBonus
			w.damageZombie(zombie, damage, ownerID, &pos, false)
		}
	}
	for _, player := range w.players {
		if !player.Alive || player.Floor != floor {
			continue
		}
		playerRadius := blastRadius * 0.65
		distance := player.Pos.Distance(pos)
		if distance <= playerRadius && !w.lineBlocked(pos, player.Pos, floor, false) {
			damage := int(float64(playerDamage)*(1-distance/playerRadius)) + playerBonus
			w.damagePlayer(player, damage)
		}
	}
}

func (w *World) damageZombie(zombie *Zombie, damage int, ownerID string, source *Vec2, revealOwner bool) {
	remaining := damage
	if zombie.Armor > 0 {
		absorbed := min(zombie.Armor, max(1, damage/3))
		zombie.Armor -= absorbed
		remaining = max(1, remaining-absorbed/2)
	}
	zombie.Health -= remaining
	if revealOwner {
		w.alertZombieFromDamage(zombie, ownerID, source)
	} else if source != nil {
		w.alertZombieFromDamage(zombie, "", source)
	}
	if zombie.Health > 0 {
		return
	}
	delete(w.zombies, zombie.ID)
	if owner := w.players[ownerID]; owner != nil {
		owner.Score++
		owner.KillsByKind[zombie.Kind]++
	}
	if w.rng.Float64() < 0.45 {
		w.dropFromZombie(zombie.Pos)
	}
}

func (w *World) damagePlayer(player *Player, damage int) {
	mitigation := w.playerArmorMitigation(player)
	remaining := max(1, int(math.Round(float64(damage)*(1-mitigation))))
	if player.Armor > 0 {
		absorbed := min(player.Armor, max(1, remaining+damage/4))
		player.Armor -= absorbed
		remaining = max(1, remaining-absorbed/4)
	}
	player.Health -= remaining
	player.HealingLeft = 0
	player.HealingPool = 0
	player.HealingStacks = 0
	if player.Health <= 0 {
		player.Health = 0
		player.Alive = false
	}
}

func (w *World) playerArmorMitigation(player *Player) float64 {
	best := 0.0
	for _, item := range player.Equipment {
		if item == nil || item.Durability <= 0 {
			continue
		}
		itemSpec := w.content.Items[item.Key]
		if itemSpec.ArmorKey == "" {
			continue
		}
		armor := w.content.Armors[itemSpec.ArmorKey]
		rarity := w.raritySpec(item.Rarity)
		best = maxFloat(best, armor.Mitigation*rarity.ArmorMitigationMultiplier)
	}
	return math.Min(0.88, best)
}

func (w *World) dropFromZombie(pos Vec2) {
	if w.rng.Float64() < 0.5 {
		w.spawnLootAt(pos, "ammo", w.randomWeaponKey(), 5+w.rng.Intn(14), 0, "common")
	} else {
		w.spawnLootAt(pos, "item", w.weightedLoot(w.content.WorldLoot), 1, 0, "common")
	}
}

func (w *World) safeRespawn() (Vec2, int, string) {
	for _, building := range w.buildings {
		for _, floor := range []int{1, 2, -1, 0} {
			if floor < building.MinFloor || floor > building.MaxFloor() {
				continue
			}
			for i := 0; i < 60; i++ {
				pos := Vec2{
					X: building.Bounds.X + 96 + w.rng.Float64()*maxFloat(1, building.Bounds.W-192),
					Y: building.Bounds.Y + 104 + w.rng.Float64()*maxFloat(1, building.Bounds.H-208),
				}
				if !w.blockedAt(pos, PlayerRadius, floor) && w.respawnIsSafe(pos, floor) {
					return pos, floor, building.ID
				}
			}
		}
	}
	for i := 0; i < 500; i++ {
		pos := w.randomOpenPos(false)
		if w.respawnIsSafe(pos, 0) {
			return pos, 0, ""
		}
	}
	return w.randomOpenPos(true), 0, ""
}

func (w *World) respawnIsSafe(pos Vec2, floor int) bool {
	for _, zombie := range w.zombies {
		if zombie.Floor != floor {
			continue
		}
		distance := zombie.Pos.Distance(pos)
		if distance < 760 {
			return false
		}
		if distance < w.zombieSpec(zombie.Kind).SightRange+140 && !w.lineBlocked(zombie.Pos, pos, floor, false) {
			return false
		}
	}
	return true
}

func (w *World) lootRarity(kind string, payload string) string {
	spec := w.content.Items[payload]
	if kind == "weapon" || kind == "armor" || (kind == "item" && spec.Kind == "armor") {
		return w.rollRarity()
	}
	return "common"
}

func (w *World) rollRarity() string {
	total := 0.0
	for _, spec := range w.content.Rarities {
		total += spec.LootWeight
	}
	if total <= 0 {
		return "common"
	}
	roll := w.rng.Float64() * total
	for key, spec := range w.content.Rarities {
		roll -= spec.LootWeight
		if roll <= 0 {
			return key
		}
	}
	return "common"
}

func (w *World) weightedLoot(items []shared.WeightedLoot) string {
	if len(items) == 0 {
		return "scrap"
	}
	total := 0.0
	for _, item := range items {
		total += item.Weight
	}
	roll := w.rng.Float64() * total
	for _, item := range items {
		roll -= item.Weight
		if roll <= 0 {
			return item.Key
		}
	}
	return items[len(items)-1].Key
}

func (w *World) weightedIndex(weights []float64) int {
	total := 0.0
	for _, weight := range weights {
		total += weight
	}
	if total <= 0 {
		return 0
	}
	roll := w.rng.Float64() * total
	for index, weight := range weights {
		roll -= weight
		if roll <= 0 {
			return index
		}
	}
	return len(weights) - 1
}

func (w *World) randomWeaponKey() string {
	keys := make([]string, 0, len(w.content.Weapons))
	for key := range w.content.Weapons {
		keys = append(keys, key)
	}
	if len(keys) == 0 {
		return "pistol"
	}
	return keys[w.rng.Intn(len(keys))]
}

func (w *World) weaponSpec(key string) shared.WeaponSpec {
	if spec, ok := w.content.Weapons[key]; ok {
		return spec
	}
	return w.content.Weapons["pistol"]
}

func (w *World) zombieSpec(key string) shared.ZombieSpec {
	if spec, ok := w.content.Zombies[key]; ok {
		return spec
	}
	return w.content.Zombies["walker"]
}

func (w *World) raritySpec(key string) shared.RaritySpec {
	if spec, ok := w.content.Rarities[key]; ok {
		return spec
	}
	return w.content.Rarities["common"]
}

func (w *World) rarityRank(key string) int {
	switch key {
	case "legendary":
		return 3
	case "rare":
		return 2
	case "uncommon":
		return 1
	default:
		return 0
	}
}

func (w *World) grenadeSpec(key string) shared.GrenadeSpec {
	if spec, ok := w.content.Grenades[key]; ok {
		return spec
	}
	return w.content.Grenades["grenade"]
}

func (w *World) mineSpec(key string) shared.MineSpec {
	if spec, ok := w.content.Mines[key]; ok {
		return spec
	}
	return w.content.Mines["mine_standard"]
}

func (w *World) setNotice(player *Player, key string, seconds float64) {
	player.Notice = key
	player.NoticeTimer = maxFloat(player.NoticeTimer, seconds)
}

func asString(v any) string {
	if text, ok := v.(string); ok {
		return text
	}
	return ""
}

func asStringDefault(v any, fallback string) string {
	if text := asString(v); text != "" {
		return text
	}
	return fallback
}

func asInt(v any, fallback int) int {
	switch value := v.(type) {
	case int:
		return value
	case int64:
		return int(value)
	case float64:
		return int(value)
	case float32:
		return int(value)
	default:
		return fallback
	}
}
