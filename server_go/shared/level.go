package shared

import "math"

const WallThickness = 22.0

func MakeBuildings() map[string]*BuildingState {
	specs := []struct {
		id   string
		name string
		x    float64
		y    float64
		w    float64
		h    float64
	}{
		{"b1", "Clinic", 3540, 2940, 760, 520},
		{"b2", "Warehouse", 11580, 3960, 920, 620},
		{"b3", "Apartments", 20460, 2520, 760, 700},
		{"b4", "Station", 6180, 12180, 820, 560},
		{"b5", "Market", 17220, 12780, 980, 600},
		{"b6", "Depot", 23880, 15360, 740, 520},
		{"b7", "Lab", 12640, 9100, 820, 600},
		{"b8", "Garage", 2480, 16240, 900, 540},
		{"b9", "Motel", 25220, 6020, 780, 660},
		{"b10", "Archive", 14320, 16440, 760, 560},
	}
	buildings := make(map[string]*BuildingState, len(specs))
	for _, spec := range specs {
		building := makeBuilding(spec.id, spec.name, spec.x, spec.y, spec.w, spec.h)
		buildings[building.ID] = building
	}
	return buildings
}

func makeBuilding(buildingID, name string, x, y, w, h float64) *BuildingState {
	firstDoorY := y + h*0.30
	secondDoorY := y + h*0.66
	walls := []RectState{
		{X: x, Y: y, W: w * 0.42, H: WallThickness},
		{X: x + w*0.58, Y: y, W: w * 0.42, H: WallThickness},
		{X: x, Y: y + h - WallThickness, W: w, H: WallThickness},
		{X: x, Y: y, W: WallThickness, H: h},
		{X: x + w - WallThickness, Y: y, W: WallThickness, H: h},
		{X: x + w*0.48, Y: y + 90, W: WallThickness, H: firstDoorY - (y + 90)},
		{X: x + w*0.48, Y: firstDoorY + 76, W: WallThickness, H: secondDoorY - (firstDoorY + 76)},
		{X: x + w*0.48, Y: secondDoorY + 76, W: WallThickness, H: y + h - 90 - (secondDoorY + 76)},
		{X: x + 120, Y: y + h*0.52, W: w * 0.34, H: WallThickness},
		{X: x + w*0.56, Y: y + h*0.45, W: w * 0.30, H: WallThickness},
	}
	doors := []DoorState{
		{ID: buildingID + "-front", Rect: RectState{X: x + w*0.42, Y: y - 6, W: w * 0.16, H: WallThickness + 12}, Floor: 0},
		{ID: buildingID + "-inside-a", Rect: RectState{X: x + w*0.48 - 5, Y: y + h*0.30, W: WallThickness + 10, H: 76}, Floor: 0},
		{ID: buildingID + "-inside-b", Rect: RectState{X: x + w*0.48 - 5, Y: y + h*0.66, W: WallThickness + 10, H: 76}, Floor: 0},
		{ID: buildingID + "-basement", Rect: RectState{X: x + w*0.42, Y: y - 6, W: w * 0.16, H: WallThickness + 12}, Floor: -1},
	}
	props := []PropState{
		{ID: buildingID + "-desk", Kind: "desk", Rect: RectState{X: x + 72, Y: y + 90, W: 96, H: 48}, Floor: 0, Blocks: true},
		{ID: buildingID + "-shelf", Kind: "shelf", Rect: RectState{X: x + w - 164, Y: y + 92, W: 88, H: 146}, Floor: 0, Blocks: true},
		{ID: buildingID + "-table", Kind: "table", Rect: RectState{X: x + w*0.60, Y: y + h*0.62, W: 136, H: 72}, Floor: 0, Blocks: true},
		{ID: buildingID + "-crate", Kind: "crate", Rect: RectState{X: x + 96, Y: y + h - 166, W: 84, H: 84}, Floor: 0, Blocks: true},
		{ID: buildingID + "-repair", Kind: "repair_table", Rect: RectState{X: x + 72, Y: y + h - 96, W: 132, H: 58}, Floor: 0, Blocks: true},
		{ID: buildingID + "-bench", Kind: "work_bench", Rect: RectState{X: x + w*0.58, Y: y + 84, W: 144, H: 62}, Floor: 1, Blocks: true},
		{ID: buildingID + "-basement-shelf", Kind: "shelf", Rect: RectState{X: x + 92, Y: y + 96, W: 92, H: 160}, Floor: -1, Blocks: true},
		{ID: buildingID + "-basement-locker", Kind: "cabinet", Rect: RectState{X: x + w - 158, Y: y + h - 238, W: 88, H: 138}, Floor: -1, Blocks: true},
		{ID: buildingID + "-upper-bed", Kind: "bed", Rect: RectState{X: x + 82, Y: y + 90, W: 142, H: 74}, Floor: 1, Blocks: true},
		{ID: buildingID + "-upper-cabinet", Kind: "cabinet", Rect: RectState{X: x + w - 150, Y: y + 100, W: 86, H: 126}, Floor: 2, Blocks: true},
		{ID: buildingID + "-glass-f2", Kind: "glass_wall", Rect: RectState{X: x + w*0.42, Y: y - 6, W: w * 0.16, H: WallThickness + 12}, Floor: 1, Blocks: true},
		{ID: buildingID + "-glass-f3", Kind: "glass_wall", Rect: RectState{X: x + w*0.42, Y: y - 6, W: w * 0.16, H: WallThickness + 12}, Floor: 2, Blocks: true},
		{ID: buildingID + "-barrel-a", Kind: "barrel", Rect: RectState{X: x - 84, Y: y + h*0.32, W: 46, H: 46}, Floor: 0, Blocks: true},
		{ID: buildingID + "-barrel-b", Kind: "barrel", Rect: RectState{X: x + w + 42, Y: y + h*0.60, W: 48, H: 48}, Floor: 0, Blocks: true},
		{ID: buildingID + "-pallet", Kind: "pallet", Rect: RectState{X: x + w*0.18, Y: y + h + 44, W: 126, H: 54}, Floor: 0, Blocks: true},
		{ID: buildingID + "-roadblock", Kind: "roadblock", Rect: RectState{X: x + w*0.68, Y: y - 84, W: 152, H: 42}, Floor: 0, Blocks: true},
	}
	return &BuildingState{
		ID:       buildingID,
		Name:     name,
		Bounds:   RectState{X: x, Y: y, W: w, H: h},
		Walls:    walls,
		Doors:    doors,
		Props:    props,
		Stairs:   []RectState{{X: x + w - 150, Y: y + h - 144, W: 94, H: 94}},
		Floors:   4,
		MinFloor: -1,
	}
}

func TunnelSegments(buildings map[string]*BuildingState) []RectState {
	order := []string{"b1", "b2", "b9", "b3", "b7", "b5", "b6", "b10", "b4", "b8", "b1"}
	centers := make([]Vec2, 0, len(order))
	for _, key := range order {
		if building := buildings[key]; building != nil {
			centers = append(centers, basementEntry(building))
		}
	}
	tunnels := make([]RectState, 0, len(centers)*2)
	width := 118.0
	for i := 0; i+1 < len(centers); i++ {
		start := centers[i]
		end := centers[i+1]
		mid := Vec2{X: end.X, Y: start.Y}
		tunnels = append(tunnels, corridor(start, mid, width), corridor(mid, end, width))
	}
	return tunnels
}

func TunnelWalls(buildings map[string]*BuildingState) []RectState {
	tunnels := TunnelSegments(buildings)
	if len(tunnels) == 0 {
		return nil
	}
	unit := 28.0
	minX, minY := math.MaxFloat64, math.MaxFloat64
	maxX, maxY := -math.MaxFloat64, -math.MaxFloat64
	for _, tunnel := range tunnels {
		minX = math.Min(minX, tunnel.X-WallThickness*2)
		minY = math.Min(minY, tunnel.Y-WallThickness*2)
		maxX = math.Max(maxX, tunnel.X+tunnel.W+WallThickness*2)
		maxY = math.Max(maxY, tunnel.Y+tunnel.H+WallThickness*2)
	}
	cols := maxInt(1, int((maxX-minX)/unit)+2)
	rows := maxInt(1, int((maxY-minY)/unit)+2)
	occupied := make([][]bool, rows)
	for row := range occupied {
		occupied[row] = make([]bool, cols)
		cy := minY + (float64(row)+0.5)*unit
		for col := 0; col < cols; col++ {
			cx := minX + (float64(col)+0.5)*unit
			for _, tunnel := range tunnels {
				if tunnel.X <= cx && cx <= tunnel.X+tunnel.W && tunnel.Y <= cy && cy <= tunnel.Y+tunnel.H {
					occupied[row][col] = true
					break
				}
			}
		}
	}
	walls := make([]RectState, 0)
	edge := WallThickness
	for row := 0; row < rows; row++ {
		for col := 0; col < cols; col++ {
			if !occupied[row][col] {
				continue
			}
			x := minX + float64(col)*unit
			y := minY + float64(row)*unit
			if row == 0 || !occupied[row-1][col] {
				walls = append(walls, RectState{X: x, Y: y - edge, W: unit, H: edge})
			}
			if row == rows-1 || !occupied[row+1][col] {
				walls = append(walls, RectState{X: x, Y: y + unit, W: unit, H: edge})
			}
			if col == 0 || !occupied[row][col-1] {
				walls = append(walls, RectState{X: x - edge, Y: y, W: edge, H: unit})
			}
			if col == cols-1 || !occupied[row][col+1] {
				walls = append(walls, RectState{X: x + unit, Y: y, W: edge, H: unit})
			}
		}
	}
	return walls
}

func AllClosedWalls(buildings map[string]*BuildingState, floor int) []RectState {
	walls := make([]RectState, 0)
	for _, building := range buildings {
		walls = append(walls, building.Walls...)
		for _, prop := range building.Props {
			if prop.Floor == floor && prop.Blocks {
				walls = append(walls, prop.Rect)
			}
		}
		for _, door := range building.Doors {
			if door.Floor == floor && !door.Open {
				walls = append(walls, door.Rect)
			}
		}
	}
	if floor == -1 {
		walls = append(walls, TunnelWalls(buildings)...)
	}
	return walls
}

func PointBuilding(buildings map[string]*BuildingState, pos Vec2) string {
	for _, building := range buildings {
		if building.Bounds.Contains(pos) {
			return building.ID
		}
	}
	return ""
}

func NearestDoor(buildings map[string]*BuildingState, pos Vec2, radius float64, floor *int) *DoorState {
	var best *DoorState
	bestDistance := radius
	for _, building := range buildings {
		for i := range building.Doors {
			door := &building.Doors[i]
			if floor != nil && door.Floor != *floor {
				continue
			}
			distance := door.Rect.Center().Distance(pos)
			if distance <= bestDistance {
				best = door
				bestDistance = distance
			}
		}
	}
	return best
}

func NearestStairs(buildings map[string]*BuildingState, pos Vec2, radius float64) *BuildingState {
	for _, building := range buildings {
		for _, stairs := range building.Stairs {
			if stairs.Inflated(radius).Contains(pos) {
				return building
			}
		}
	}
	return nil
}

func NearestProp(buildings map[string]*BuildingState, pos Vec2, radius float64, kind string, floor int) *PropState {
	var best *PropState
	bestDistance := radius
	for _, building := range buildings {
		for i := range building.Props {
			prop := &building.Props[i]
			if prop.Kind != kind || prop.Floor != floor {
				continue
			}
			distance := prop.Rect.Center().Distance(pos)
			if distance <= bestDistance {
				best = prop
				bestDistance = distance
			}
		}
	}
	return best
}

func basementEntry(building *BuildingState) Vec2 {
	return Vec2{X: building.Bounds.X + building.Bounds.W*0.5, Y: building.Bounds.Y + WallThickness*0.5}
}

func corridor(start, end Vec2, width float64) RectState {
	if math.Abs(start.X-end.X) >= math.Abs(start.Y-end.Y) {
		x := math.Min(start.X, end.X)
		return RectState{X: x, Y: start.Y - width*0.5, W: math.Abs(start.X - end.X), H: width}
	}
	y := math.Min(start.Y, end.Y)
	return RectState{X: start.X - width*0.5, Y: y, W: width, H: math.Abs(start.Y - end.Y)}
}
