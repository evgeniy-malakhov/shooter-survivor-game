package shared

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
)

type Content struct {
	Weapons       map[string]WeaponSpec
	Armors        map[string]ArmorSpec
	Zombies       map[string]ZombieSpec
	Rarities      map[string]RaritySpec
	Items         map[string]ItemSpec
	Recipes       map[string]RecipeSpec
	Grenades      map[string]GrenadeSpec
	Mines         map[string]MineSpec
	WeaponModules map[string]WeaponModuleSpec
	Backpack      BackpackConfig
	HouseLoot     []WeightedLoot
	BasementLoot  []WeightedLoot
	WorldLoot     []WeightedLoot
}

func LoadContent(configDir string) (*Content, error) {
	if configDir == "" {
		configDir = DefaultConfigDir()
	}
	content := DefaultContent()
	var errs []error
	if err := loadWeapons(filepath.Join(configDir, "weapons.json"), content.Weapons); err != nil {
		errs = append(errs, err)
	}
	if err := loadArmors(filepath.Join(configDir, "armors.json"), content.Armors); err != nil {
		errs = append(errs, err)
	}
	if err := loadZombies(filepath.Join(configDir, "zombies.json"), content.Zombies); err != nil {
		errs = append(errs, err)
	}
	if err := loadRarities(filepath.Join(configDir, "rarities.json"), content.Rarities); err != nil {
		errs = append(errs, err)
	}
	if err := loadExplosives(filepath.Join(configDir, "explosives.json"), content.Grenades, content.Mines); err != nil {
		errs = append(errs, err)
	}
	if err := loadWeaponModules(filepath.Join(configDir, "weapon_modules.json"), content.WeaponModules); err != nil {
		errs = append(errs, err)
	}
	if stacks, err := loadStackSizes(filepath.Join(configDir, "item_stacks.json")); err == nil {
		content.Items = DefaultItems(stacks)
	} else {
		errs = append(errs, err)
	}
	if backpack, err := loadBackpack(filepath.Join(configDir, "backpack.json")); err == nil {
		content.Backpack = backpack
	} else {
		errs = append(errs, err)
	}
	if err := loadCrafting(filepath.Join(configDir, "crafting.json")); err != nil {
		errs = append(errs, err)
	}
	if len(errs) > 0 {
		return content, errors.Join(errs...)
	}
	return content, nil
}

func DefaultConfigDir() string {
	candidates := []string{
		filepath.Join("..", "configs"),
		"configs",
		filepath.Join("..", "..", "configs"),
		filepath.Join("server_go", "configs"),
	}
	for _, candidate := range candidates {
		if info, err := os.Stat(candidate); err == nil && info.IsDir() {
			return candidate
		}
	}
	return "configs"
}

func DefaultContent() *Content {
	stacks := map[string]int{}
	return &Content{
		Weapons:       DefaultWeapons(),
		Armors:        DefaultArmors(),
		Zombies:       DefaultZombies(),
		Rarities:      DefaultRarities(),
		Items:         DefaultItems(stacks),
		Recipes:       DefaultRecipes(),
		Grenades:      DefaultGrenades(),
		Mines:         DefaultMines(),
		WeaponModules: DefaultWeaponModules(),
		Backpack: BackpackConfig{
			Slots:          30,
			StartingWeapon: StartingWeapon{Key: "pistol", ReserveAmmo: 48},
			StartingItems: []StartingItem{
				{Key: "apple", Amount: 2},
				{Key: "bandage", Amount: 1},
				{Key: "cloth", Amount: 2},
			},
		},
		HouseLoot: []WeightedLoot{
			{Key: "apple", Min: 1, Weight: 5},
			{Key: "canned_food", Min: 1, Weight: 4},
			{Key: "energy_bar", Min: 1, Weight: 5},
			{Key: "bandage", Min: 1, Weight: 3},
			{Key: "medicine", Min: 1, Weight: 2},
			{Key: "cloth", Min: 1, Weight: 4},
			{Key: "duct_tape", Min: 1, Weight: 3},
			{Key: "scrap", Min: 1, Weight: 5},
			{Key: "circuit", Min: 1, Weight: 2},
			{Key: "repair_kit", Min: 1, Weight: 1},
			{Key: "contact_grenade", Min: 1, Weight: 1},
			{Key: "grenade", Min: 1, Weight: 1},
			{Key: "mine_light", Min: 1, Weight: 1},
			{Key: "light_head", Min: 1, Weight: 1},
			{Key: "light_torso", Min: 1, Weight: 1},
		},
		BasementLoot: []WeightedLoot{
			{Key: "repair_kit", Min: 1, Weight: 4},
			{Key: "circuit", Min: 1, Weight: 4},
			{Key: "gunpowder", Min: 1, Weight: 4},
			{Key: "heavy_grenade", Min: 1, Weight: 3},
			{Key: "mine_standard", Min: 1, Weight: 3},
			{Key: "mine_heavy", Min: 1, Weight: 2},
			{Key: "laser_module", Min: 1, Weight: 2},
			{Key: "flashlight_module", Min: 1, Weight: 2},
			{Key: "extended_mag", Min: 1, Weight: 2},
		},
		WorldLoot: []WeightedLoot{
			{Key: "apple", Min: 1, Weight: 2},
			{Key: "scrap", Min: 1, Weight: 5},
			{Key: "cloth", Min: 1, Weight: 4},
			{Key: "gunpowder", Min: 1, Weight: 3},
			{Key: "duct_tape", Min: 1, Weight: 2},
			{Key: "ammo_pack", Min: 1, Weight: 4},
			{Key: "grenade", Min: 1, Weight: 1},
			{Key: "mine_light", Min: 1, Weight: 1},
			{Key: "light_torso", Min: 1, Weight: 1},
		},
	}
}

func DefaultWeapons() map[string]WeaponSpec {
	return map[string]WeaponSpec{
		"pistol":  {Key: "pistol", Title: "Viper Pistol", Slot: "1", Damage: 18, MagazineSize: 12, FireRate: 4.5, ReloadTime: 1.1, ProjectileSpeed: 980, Spread: 0.035, Pellets: 1},
		"smg":     {Key: "smg", Title: "Pulse SMG", Slot: "2", Damage: 10, MagazineSize: 28, FireRate: 12, ReloadTime: 1.6, ProjectileSpeed: 920, Spread: 0.075, Pellets: 1},
		"shotgun": {Key: "shotgun", Title: "Breaker Shotgun", Slot: "3", Damage: 12, MagazineSize: 6, FireRate: 1.2, ReloadTime: 1.9, ProjectileSpeed: 780, Spread: 0.18, Pellets: 7},
		"rifle":   {Key: "rifle", Title: "Arc Rifle", Slot: "4", Damage: 32, MagazineSize: 20, FireRate: 5, ReloadTime: 1.9, ProjectileSpeed: 1180, Spread: 0.025, Pellets: 1},
	}
}

func DefaultArmors() map[string]ArmorSpec {
	return map[string]ArmorSpec{
		"none":     {Key: "none", Title: "No Armor", Mitigation: 0, ArmorPoints: 0},
		"light":    {Key: "light", Title: "Light Vest", Mitigation: 0.18, ArmorPoints: 45},
		"medium":   {Key: "medium", Title: "Medium Armor", Mitigation: 0.30, ArmorPoints: 72},
		"tactical": {Key: "tactical", Title: "Tactical Rig", Mitigation: 0.30, ArmorPoints: 70},
		"heavy":    {Key: "heavy", Title: "Heavy Plate", Mitigation: 0.42, ArmorPoints: 110},
	}
}

func DefaultZombies() map[string]ZombieSpec {
	return map[string]ZombieSpec{
		"walker": {Key: "walker", Title: "Walker", Health: 70, Armor: 0, Speed: 92, Damage: 13, Radius: 24, Color: [3]int{114, 222, 158}, SightRange: 540, HearingRange: 430, FOVDegrees: 116, Sensitivity: 0.85, SuspicionTime: 1.4},
		"runner": {Key: "runner", Title: "Runner", Health: 38, Armor: 0, Speed: 165, Damage: 9, Radius: 19, Color: [3]int{255, 101, 112}, SightRange: 620, HearingRange: 620, FOVDegrees: 132, Sensitivity: 1.25, SuspicionTime: 0.9},
		"brute":  {Key: "brute", Title: "Brute", Health: 115, Armor: 55, Speed: 62, Damage: 21, Radius: 31, Color: [3]int{127, 164, 255}, SightRange: 470, HearingRange: 360, FOVDegrees: 94, Sensitivity: 0.65, SuspicionTime: 1.8},
		"leaper": {Key: "leaper", Title: "Leaper", Health: 64, Armor: 10, Speed: 188, Damage: 11, Radius: 20, Color: [3]int{92, 246, 124}, SightRange: 660, HearingRange: 560, FOVDegrees: 124, Sensitivity: 1.05, SuspicionTime: 1.0},
	}
}

func DefaultRarities() map[string]RaritySpec {
	return map[string]RaritySpec{
		"common":    {Key: "common", Title: "Common", Color: [3]int{145, 154, 166}, LootWeight: 64, WeaponDamageMultiplier: 1, WeaponDurabilityMultiplier: 1, ArmorPointsMultiplier: 1, ArmorMitigationMultiplier: 1, ArmorDurabilityMultiplier: 1},
		"uncommon":  {Key: "uncommon", Title: "Uncommon", Color: [3]int{88, 205, 255}, LootWeight: 24, WeaponDamageMultiplier: 1.10, WeaponDurabilityMultiplier: 1.12, ArmorPointsMultiplier: 1.12, ArmorMitigationMultiplier: 1.07, ArmorDurabilityMultiplier: 1.12},
		"rare":      {Key: "rare", Title: "Rare", Color: [3]int{178, 112, 255}, LootWeight: 9, WeaponDamageMultiplier: 1.22, WeaponDurabilityMultiplier: 1.28, ArmorPointsMultiplier: 1.28, ArmorMitigationMultiplier: 1.14, ArmorDurabilityMultiplier: 1.28},
		"legendary": {Key: "legendary", Title: "Legendary", Color: [3]int{255, 211, 92}, LootWeight: 3, WeaponDamageMultiplier: 1.38, WeaponDurabilityMultiplier: 1.5, ArmorPointsMultiplier: 1.48, ArmorMitigationMultiplier: 1.22, ArmorDurabilityMultiplier: 1.5},
	}
}

func DefaultItems(stacks map[string]int) map[string]ItemSpec {
	stack := func(key string, fallback int) int {
		if value := stacks[key]; value > 0 {
			return value
		}
		return fallback
	}
	items := map[string]ItemSpec{
		"apple":             {Key: "apple", Title: "Apple", Kind: "food", StackSize: stack("apple", 8), HealTotal: 12, HealSeconds: 5, Color: [3]int{132, 232, 114}},
		"canned_food":       {Key: "canned_food", Title: "Canned Food", Kind: "food", StackSize: stack("canned_food", 6), HealTotal: 24, HealSeconds: 8, Color: [3]int{235, 186, 92}},
		"energy_bar":        {Key: "energy_bar", Title: "Energy Bar", Kind: "food", StackSize: stack("energy_bar", 10), HealTotal: 16, HealSeconds: 4, Color: [3]int{246, 220, 92}},
		"bandage":           {Key: "bandage", Title: "Bandage", Kind: "medical", StackSize: stack("bandage", 6), HealTotal: 28, HealSeconds: 7, Color: [3]int{244, 244, 224}},
		"medicine":          {Key: "medicine", Title: "Medicine", Kind: "medical", StackSize: stack("medicine", 4), HealTotal: 45, HealSeconds: 10, Color: [3]int{118, 226, 255}},
		"scrap":             {Key: "scrap", Title: "Scrap Metal", Kind: "resource", StackSize: stack("scrap", 20), Color: [3]int{154, 164, 178}},
		"cloth":             {Key: "cloth", Title: "Cloth", Kind: "resource", StackSize: stack("cloth", 20), Color: [3]int{192, 184, 160}},
		"duct_tape":         {Key: "duct_tape", Title: "Duct Tape", Kind: "resource", StackSize: stack("duct_tape", 12), Color: [3]int{164, 174, 198}},
		"circuit":           {Key: "circuit", Title: "Circuit Board", Kind: "resource", StackSize: stack("circuit", 10), Color: [3]int{80, 220, 150}},
		"gunpowder":         {Key: "gunpowder", Title: "Gunpowder", Kind: "resource", StackSize: stack("gunpowder", 20), Color: [3]int{96, 96, 106}},
		"ammo_pack":         {Key: "ammo_pack", Title: "Ammo Pack", Kind: "ammo", StackSize: stack("ammo_pack", 12), Color: [3]int{255, 210, 112}},
		"contact_grenade":   {Key: "contact_grenade", Title: "Impact Grenade", Kind: "grenade", StackSize: stack("contact_grenade", 3), Color: [3]int{103, 236, 190}},
		"grenade":           {Key: "grenade", Title: "Grenade", Kind: "grenade", StackSize: stack("grenade", 4), Color: [3]int{96, 180, 108}},
		"heavy_grenade":     {Key: "heavy_grenade", Title: "Heavy Grenade", Kind: "grenade", StackSize: stack("heavy_grenade", 2), Color: [3]int{255, 128, 92}},
		"mine_light":        {Key: "mine_light", Title: "Light Mine", Kind: "mine", StackSize: stack("mine_light", 3), Color: [3]int{120, 225, 255}},
		"mine_standard":     {Key: "mine_standard", Title: "Field Mine", Kind: "mine", StackSize: stack("mine_standard", 3), Color: [3]int{255, 210, 112}},
		"mine_heavy":        {Key: "mine_heavy", Title: "Heavy Mine", Kind: "mine", StackSize: stack("mine_heavy", 2), Color: [3]int{255, 91, 111}},
		"repair_kit":        {Key: "repair_kit", Title: "Repair Kit", Kind: "tool", StackSize: stack("repair_kit", 4), Color: [3]int{255, 146, 100}},
		"laser_module":      {Key: "laser_module", Title: "Laser Sight", Kind: "weapon_module", StackSize: stack("laser_module", 1), Color: [3]int{255, 84, 98}},
		"flashlight_module": {Key: "flashlight_module", Title: "Flashlight", Kind: "weapon_module", StackSize: stack("flashlight_module", 1), Color: [3]int{255, 238, 148}},
		"silencer":          {Key: "silencer", Title: "Silencer", Kind: "weapon_module", StackSize: stack("silencer", 1), Color: [3]int{156, 198, 255}},
		"compensator":       {Key: "compensator", Title: "Compensator", Kind: "weapon_module", StackSize: stack("compensator", 1), Color: [3]int{255, 196, 142}},
		"extended_mag":      {Key: "extended_mag", Title: "Extended Magazine", Kind: "weapon_module", StackSize: stack("extended_mag", 1), Color: [3]int{116, 204, 255}},
	}
	levels := map[string][3]int{"light": {152, 204, 255}, "medium": {177, 132, 255}, "heavy": {126, 154, 255}}
	titles := map[string]string{"head": "Helmet", "torso": "Vest", "arms": "Guards", "legs": "Plates"}
	for level, color := range levels {
		for slot, title := range titles {
			key := level + "_" + slot
			items[key] = ItemSpec{Key: key, Title: title, Kind: "armor", StackSize: stack(key, 1), EquipmentSlot: slot, ArmorKey: level, Color: color}
		}
	}
	return items
}

func DefaultRecipes() map[string]RecipeSpec {
	recipes := map[string]RecipeSpec{
		"bandage_bundle":    {Key: "bandage_bundle", Title: "Bandage Bundle", Requires: map[string]int{"cloth": 3, "duct_tape": 1}, ResultKey: "bandage", ResultQty: 2},
		"repair_kit":        {Key: "repair_kit", Title: "Repair Kit", Requires: map[string]int{"scrap": 4, "duct_tape": 2}, ResultKey: "repair_kit", ResultQty: 1},
		"ammo_pack":         {Key: "ammo_pack", Title: "Ammo Pack", Requires: map[string]int{"scrap": 2, "gunpowder": 3}, ResultKey: "ammo_pack", ResultQty: 2},
		"grenade":           {Key: "grenade", Title: "Grenade", Requires: map[string]int{"scrap": 3, "gunpowder": 5, "duct_tape": 1}, ResultKey: "grenade", ResultQty: 1},
		"heavy_grenade":     {Key: "heavy_grenade", Title: "Heavy Grenade", Requires: map[string]int{"scrap": 5, "gunpowder": 9, "duct_tape": 2}, ResultKey: "heavy_grenade", ResultQty: 1},
		"mine_standard":     {Key: "mine_standard", Title: "Field Mine", Requires: map[string]int{"scrap": 5, "gunpowder": 5, "circuit": 1, "duct_tape": 1}, ResultKey: "mine_standard", ResultQty: 1},
		"laser_module":      {Key: "laser_module", Title: "Laser Sight", Requires: map[string]int{"circuit": 1, "scrap": 2, "duct_tape": 1}, ResultKey: "laser_module", ResultQty: 1},
		"flashlight_module": {Key: "flashlight_module", Title: "Flashlight", Requires: map[string]int{"circuit": 1, "scrap": 2, "cloth": 1}, ResultKey: "flashlight_module", ResultQty: 1},
		"extended_mag":      {Key: "extended_mag", Title: "Extended Magazine", Requires: map[string]int{"scrap": 4, "duct_tape": 1}, ResultKey: "extended_mag", ResultQty: 1},
	}
	for _, slot := range EquipmentSlots {
		recipes["medium_"+slot] = RecipeSpec{Key: "medium_" + slot, Title: "Medium " + slot, Requires: map[string]int{"cloth": 4, "scrap": 5, "duct_tape": 2}, ResultKey: "medium_" + slot, ResultQty: 1}
		recipes["heavy_"+slot] = RecipeSpec{Key: "heavy_" + slot, Title: "Heavy " + slot, Requires: map[string]int{"cloth": 5, "scrap": 8, "duct_tape": 3, "circuit": 1}, ResultKey: "heavy_" + slot, ResultQty: 1}
	}
	return recipes
}

func DefaultGrenades() map[string]GrenadeSpec {
	return map[string]GrenadeSpec{
		"contact_grenade": {Key: "contact_grenade", Title: "Impact Grenade", Timer: 4, Contact: true, ThrowDistance: 650, BlastRadius: 190, ZombieDamage: 95, ZombieDamageBonus: 24, PlayerDamage: 35, PlayerDamageBonus: 7},
		"grenade":         {Key: "grenade", Title: "Fragmentation Grenade", Timer: 2, Contact: false, ThrowDistance: 420, BlastRadius: 220, ZombieDamage: 115, ZombieDamageBonus: 28, PlayerDamage: 42, PlayerDamageBonus: 8},
		"heavy_grenade":   {Key: "heavy_grenade", Title: "Heavy Grenade", Timer: 3, Contact: false, ThrowDistance: 340, BlastRadius: 440, ZombieDamage: 230, ZombieDamageBonus: 56, PlayerDamage: 84, PlayerDamageBonus: 16},
	}
}

func DefaultMines() map[string]MineSpec {
	return map[string]MineSpec{
		"mine_light":    {Key: "mine_light", Title: "Light Mine", TriggerRadius: 86, BlastRadius: 170, ZombieDamage: 80, ZombieDamageBonus: 20, PlayerDamage: 32, PlayerDamageBonus: 8},
		"mine_standard": {Key: "mine_standard", Title: "Field Mine", TriggerRadius: 104, BlastRadius: 230, ZombieDamage: 125, ZombieDamageBonus: 32, PlayerDamage: 48, PlayerDamageBonus: 12},
		"mine_heavy":    {Key: "mine_heavy", Title: "Heavy Mine", TriggerRadius: 122, BlastRadius: 310, ZombieDamage: 190, ZombieDamageBonus: 46, PlayerDamage: 72, PlayerDamageBonus: 18},
	}
}

func DefaultWeaponModules() map[string]WeaponModuleSpec {
	return map[string]WeaponModuleSpec{
		"laser_module":      {Key: "laser_module", Slot: "utility", Title: "Laser Sight", BeamLength: 760, SpreadMultiplier: 0.88, MagazineMultiplier: 1, NoiseMultiplier: 1},
		"flashlight_module": {Key: "flashlight_module", Slot: "utility", Title: "Flashlight", ConeRange: 620, ConeDegrees: 58, SpreadMultiplier: 1, MagazineMultiplier: 1, NoiseMultiplier: 1},
		"silencer":          {Key: "silencer", Slot: "utility", Title: "Silencer", SpreadMultiplier: 1.08, MagazineMultiplier: 1, NoiseMultiplier: 0},
		"compensator":       {Key: "compensator", Slot: "utility", Title: "Compensator", SpreadMultiplier: 0.95, MagazineMultiplier: 1, NoiseMultiplier: 1.12, FireRateBonus: 0.03, FireRateRarityStep: 0.02},
		"extended_mag":      {Key: "extended_mag", Slot: "magazine", Title: "Extended Magazine", SpreadMultiplier: 1, MagazineMultiplier: 1.16, NoiseMultiplier: 1},
	}
}

func loadWeapons(path string, dst map[string]WeaponSpec) error {
	raw := map[string]struct {
		Title           string  `json:"title"`
		Slot            string  `json:"slot"`
		Damage          int     `json:"damage"`
		MagazineSize    int     `json:"magazine_size"`
		FireRate        float64 `json:"fire_rate"`
		ReloadTime      float64 `json:"reload_time"`
		ProjectileSpeed float64 `json:"projectile_speed"`
		Spread          float64 `json:"spread"`
		Pellets         int     `json:"pellets"`
	}{}
	if err := readJSON(path, &raw); err != nil {
		return err
	}
	for key, spec := range raw {
		fallback := dst[key]
		if fallback.Key == "" {
			fallback = dst["pistol"]
		}
		slot := spec.Slot
		if !SlotExists(slot) {
			slot = fallback.Slot
		}
		dst[key] = WeaponSpec{
			Key:             key,
			Title:           fallbackString(spec.Title, fallback.Title),
			Slot:            slot,
			Damage:          maxInt(1, fallbackInt(spec.Damage, fallback.Damage)),
			MagazineSize:    maxInt(1, fallbackInt(spec.MagazineSize, fallback.MagazineSize)),
			FireRate:        maxFloat(0.1, fallbackFloat(spec.FireRate, fallback.FireRate)),
			ReloadTime:      maxFloat(0.05, fallbackFloat(spec.ReloadTime, fallback.ReloadTime)),
			ProjectileSpeed: maxFloat(10, fallbackFloat(spec.ProjectileSpeed, fallback.ProjectileSpeed)),
			Spread:          maxFloat(0, fallbackFloat(spec.Spread, fallback.Spread)),
			Pellets:         maxInt(1, fallbackInt(spec.Pellets, fallback.Pellets)),
		}
	}
	return nil
}

func loadArmors(path string, dst map[string]ArmorSpec) error {
	raw := map[string]struct {
		Title       string  `json:"title"`
		Mitigation  float64 `json:"mitigation"`
		ArmorPoints int     `json:"armor_points"`
	}{}
	if err := readJSON(path, &raw); err != nil {
		return err
	}
	for key, spec := range raw {
		fallback := dst[key]
		dst[key] = ArmorSpec{
			Key:         key,
			Title:       fallbackString(spec.Title, fallback.Title),
			Mitigation:  Clamp(fallbackFloat(spec.Mitigation, fallback.Mitigation), 0, 0.92),
			ArmorPoints: maxInt(0, fallbackInt(spec.ArmorPoints, fallback.ArmorPoints)),
		}
	}
	return nil
}

func loadZombies(path string, dst map[string]ZombieSpec) error {
	raw := map[string]struct {
		Title         string  `json:"title"`
		Health        int     `json:"health"`
		Armor         int     `json:"armor"`
		Speed         float64 `json:"speed"`
		Damage        int     `json:"damage"`
		Radius        float64 `json:"radius"`
		Color         []int   `json:"color"`
		SightRange    float64 `json:"sight_range"`
		HearingRange  float64 `json:"hearing_range"`
		FOVDegrees    float64 `json:"fov_degrees"`
		Sensitivity   float64 `json:"sensitivity"`
		SuspicionTime float64 `json:"suspicion_time"`
	}{}
	if err := readJSON(path, &raw); err != nil {
		return err
	}
	for key, spec := range raw {
		fallback := dst[key]
		dst[key] = ZombieSpec{
			Key:           key,
			Title:         fallbackString(spec.Title, fallback.Title),
			Health:        maxInt(1, fallbackInt(spec.Health, fallback.Health)),
			Armor:         maxInt(0, fallbackInt(spec.Armor, fallback.Armor)),
			Speed:         maxFloat(1, fallbackFloat(spec.Speed, fallback.Speed)),
			Damage:        maxInt(1, fallbackInt(spec.Damage, fallback.Damage)),
			Radius:        maxFloat(4, fallbackFloat(spec.Radius, fallback.Radius)),
			Color:         color(spec.Color, fallback.Color),
			SightRange:    maxFloat(1, fallbackFloat(spec.SightRange, fallback.SightRange)),
			HearingRange:  maxFloat(1, fallbackFloat(spec.HearingRange, fallback.HearingRange)),
			FOVDegrees:    Clamp(fallbackFloat(spec.FOVDegrees, fallback.FOVDegrees), 1, 360),
			Sensitivity:   maxFloat(0, fallbackFloat(spec.Sensitivity, fallback.Sensitivity)),
			SuspicionTime: maxFloat(0, fallbackFloat(spec.SuspicionTime, fallback.SuspicionTime)),
		}
	}
	return nil
}

func loadRarities(path string, dst map[string]RaritySpec) error {
	raw := map[string]struct {
		Title                      string  `json:"title"`
		Color                      []int   `json:"color"`
		LootWeight                 float64 `json:"loot_weight"`
		WeaponDamageMultiplier     float64 `json:"weapon_damage_multiplier"`
		WeaponDurabilityMultiplier float64 `json:"weapon_durability_multiplier"`
		ArmorPointsMultiplier      float64 `json:"armor_points_multiplier"`
		ArmorMitigationMultiplier  float64 `json:"armor_mitigation_multiplier"`
		ArmorDurabilityMultiplier  float64 `json:"armor_durability_multiplier"`
	}{}
	if err := readJSON(path, &raw); err != nil {
		return err
	}
	for key, spec := range raw {
		fallback := dst[key]
		dst[key] = RaritySpec{
			Key:                        key,
			Title:                      fallbackString(spec.Title, fallback.Title),
			Color:                      color(spec.Color, fallback.Color),
			LootWeight:                 maxFloat(0, fallbackFloat(spec.LootWeight, fallback.LootWeight)),
			WeaponDamageMultiplier:     maxFloat(0.1, fallbackFloat(spec.WeaponDamageMultiplier, fallback.WeaponDamageMultiplier)),
			WeaponDurabilityMultiplier: maxFloat(0.1, fallbackFloat(spec.WeaponDurabilityMultiplier, fallback.WeaponDurabilityMultiplier)),
			ArmorPointsMultiplier:      maxFloat(0.1, fallbackFloat(spec.ArmorPointsMultiplier, fallback.ArmorPointsMultiplier)),
			ArmorMitigationMultiplier:  maxFloat(0.1, fallbackFloat(spec.ArmorMitigationMultiplier, fallback.ArmorMitigationMultiplier)),
			ArmorDurabilityMultiplier:  maxFloat(0.1, fallbackFloat(spec.ArmorDurabilityMultiplier, fallback.ArmorDurabilityMultiplier)),
		}
	}
	return nil
}

func loadExplosives(path string, grenades map[string]GrenadeSpec, mines map[string]MineSpec) error {
	type grenadeJSON struct {
		Title             string  `json:"title"`
		Timer             float64 `json:"timer"`
		Contact           bool    `json:"contact"`
		ThrowDistance     float64 `json:"throw_distance"`
		BlastRadius       float64 `json:"blast_radius"`
		ZombieDamage      int     `json:"zombie_damage"`
		ZombieDamageBonus int     `json:"zombie_damage_bonus"`
		PlayerDamage      int     `json:"player_damage"`
		PlayerDamageBonus int     `json:"player_damage_bonus"`
	}
	type mineJSON struct {
		Title             string  `json:"title"`
		TriggerRadius     float64 `json:"trigger_radius"`
		BlastRadius       float64 `json:"blast_radius"`
		ZombieDamage      int     `json:"zombie_damage"`
		ZombieDamageBonus int     `json:"zombie_damage_bonus"`
		PlayerDamage      int     `json:"player_damage"`
		PlayerDamageBonus int     `json:"player_damage_bonus"`
	}
	raw := struct {
		Grenades map[string]grenadeJSON `json:"grenades"`
		Mines    map[string]mineJSON    `json:"mines"`
	}{}
	if err := readJSON(path, &raw); err != nil {
		return err
	}
	for key, spec := range raw.Grenades {
		fallback := grenades[key]
		grenades[key] = GrenadeSpec{
			Key:               key,
			Title:             fallbackString(spec.Title, fallback.Title),
			Timer:             maxFloat(0.05, fallbackFloat(spec.Timer, fallback.Timer)),
			Contact:           spec.Contact,
			ThrowDistance:     maxFloat(80, fallbackFloat(spec.ThrowDistance, fallback.ThrowDistance)),
			BlastRadius:       maxFloat(20, fallbackFloat(spec.BlastRadius, fallback.BlastRadius)),
			ZombieDamage:      maxInt(1, fallbackInt(spec.ZombieDamage, fallback.ZombieDamage)),
			ZombieDamageBonus: maxInt(0, fallbackInt(spec.ZombieDamageBonus, fallback.ZombieDamageBonus)),
			PlayerDamage:      maxInt(1, fallbackInt(spec.PlayerDamage, fallback.PlayerDamage)),
			PlayerDamageBonus: maxInt(0, fallbackInt(spec.PlayerDamageBonus, fallback.PlayerDamageBonus)),
		}
	}
	for key, spec := range raw.Mines {
		fallback := mines[key]
		mines[key] = MineSpec{
			Key:               key,
			Title:             fallbackString(spec.Title, fallback.Title),
			TriggerRadius:     maxFloat(24, fallbackFloat(spec.TriggerRadius, fallback.TriggerRadius)),
			BlastRadius:       maxFloat(40, fallbackFloat(spec.BlastRadius, fallback.BlastRadius)),
			ZombieDamage:      maxInt(1, fallbackInt(spec.ZombieDamage, fallback.ZombieDamage)),
			ZombieDamageBonus: maxInt(0, fallbackInt(spec.ZombieDamageBonus, fallback.ZombieDamageBonus)),
			PlayerDamage:      maxInt(1, fallbackInt(spec.PlayerDamage, fallback.PlayerDamage)),
			PlayerDamageBonus: maxInt(0, fallbackInt(spec.PlayerDamageBonus, fallback.PlayerDamageBonus)),
		}
	}
	return nil
}

func loadWeaponModules(path string, modules map[string]WeaponModuleSpec) error {
	raw := map[string]struct {
		Slot               string  `json:"slot"`
		Title              string  `json:"title"`
		BeamLength         float64 `json:"beam_length"`
		ConeRange          float64 `json:"cone_range"`
		ConeDegrees        float64 `json:"cone_degrees"`
		SpreadMultiplier   float64 `json:"spread_multiplier"`
		MagazineMultiplier float64 `json:"magazine_multiplier"`
		NoiseMultiplier    float64 `json:"noise_multiplier"`
		FireRateBonus      float64 `json:"fire_rate_bonus"`
		FireRateRarityStep float64 `json:"fire_rate_rarity_step"`
	}{}
	if err := readJSON(path, &raw); err != nil {
		return err
	}
	for key, spec := range raw {
		fallback := modules[key]
		modules[key] = WeaponModuleSpec{
			Key:                key,
			Title:              fallbackString(spec.Title, fallback.Title),
			Slot:               fallbackString(spec.Slot, fallbackString(fallback.Slot, "utility")),
			BeamLength:         fallbackFloat(spec.BeamLength, fallback.BeamLength),
			ConeRange:          fallbackFloat(spec.ConeRange, fallback.ConeRange),
			ConeDegrees:        fallbackFloat(spec.ConeDegrees, fallback.ConeDegrees),
			SpreadMultiplier:   maxFloat(0.05, fallbackFloat(spec.SpreadMultiplier, fallback.SpreadMultiplier)),
			MagazineMultiplier: maxFloat(1, fallbackFloat(spec.MagazineMultiplier, fallback.MagazineMultiplier)),
			NoiseMultiplier:    maxFloat(0, fallbackFloat(spec.NoiseMultiplier, fallback.NoiseMultiplier)),
			FireRateBonus:      maxFloat(0, fallbackFloat(spec.FireRateBonus, fallback.FireRateBonus)),
			FireRateRarityStep: maxFloat(0, fallbackFloat(spec.FireRateRarityStep, fallback.FireRateRarityStep)),
		}
	}
	return nil
}

func loadStackSizes(path string) (map[string]int, error) {
	stacks := map[string]int{}
	if err := readJSON(path, &stacks); err != nil {
		return stacks, err
	}
	for key, value := range stacks {
		if value < 1 {
			stacks[key] = 1
		}
	}
	return stacks, nil
}

func loadBackpack(path string) (BackpackConfig, error) {
	raw := struct {
		Slots          int `json:"slots"`
		StartingWeapon struct {
			Key         string `json:"key"`
			ReserveAmmo int    `json:"reserve_ammo"`
		} `json:"starting_weapon"`
		StartingItems []struct {
			Key    string `json:"key"`
			Amount int    `json:"amount"`
		} `json:"starting_items"`
	}{}
	if err := readJSON(path, &raw); err != nil {
		return BackpackConfig{}, err
	}
	cfg := BackpackConfig{
		Slots:          maxInt(10, minInt(80, raw.Slots)),
		StartingWeapon: StartingWeapon{Key: fallbackString(raw.StartingWeapon.Key, "pistol"), ReserveAmmo: maxInt(0, raw.StartingWeapon.ReserveAmmo)},
	}
	for _, item := range raw.StartingItems {
		if item.Key != "" {
			cfg.StartingItems = append(cfg.StartingItems, StartingItem{Key: item.Key, Amount: maxInt(1, item.Amount)})
		}
	}
	if len(cfg.StartingItems) == 0 {
		cfg.StartingItems = []StartingItem{{Key: "apple", Amount: 2}, {Key: "bandage", Amount: 1}, {Key: "cloth", Amount: 2}}
	}
	return cfg, nil
}

func loadCrafting(path string) error {
	var raw map[string]any
	return readJSON(path, &raw)
}

func readJSON(path string, dst any) error {
	raw, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	return json.Unmarshal(raw, dst)
}

func color(raw []int, fallback [3]int) [3]int {
	if len(raw) != 3 {
		return fallback
	}
	return [3]int{clampInt(raw[0], 0, 255), clampInt(raw[1], 0, 255), clampInt(raw[2], 0, 255)}
}

func fallbackString(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

func fallbackInt(value, fallback int) int {
	if value == 0 {
		return fallback
	}
	return value
}

func fallbackFloat(value, fallback float64) float64 {
	if value == 0 {
		return fallback
	}
	return value
}

func clampInt(value, low, high int) int {
	if value < low {
		return low
	}
	if value > high {
		return high
	}
	return value
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func maxFloat(a, b float64) float64 {
	if a > b {
		return a
	}
	return b
}
