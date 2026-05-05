package shared

import "math"

const (
	collisionSkin  = 0.04
	resolveEpsilon = 0.01
)

func MoveCircleAgainstRects(pos Vec2, delta Vec2, radius float64, walls []RectState) Vec2 {
	if len(walls) == 0 {
		return pos.Add(delta)
	}
	pos = ResolveCirclePenetration(pos, radius, walls)
	distance := delta.Length()
	steps := maxInt(1, int(math.Ceil(distance/math.Max(4.0, radius*0.35))))
	stepX := delta.X / float64(steps)
	stepY := delta.Y / float64(steps)
	for i := 0; i < steps; i++ {
		pos = moveAxis(pos, stepX, "x", radius, walls)
		pos = moveAxis(pos, stepY, "y", radius, walls)
	}
	return ResolveCirclePenetration(pos, radius, walls)
}

func BlockedAt(pos Vec2, radius float64, walls []RectState) bool {
	for _, wall := range walls {
		if CircleRectIntersects(pos, radius, wall) {
			return true
		}
	}
	return false
}

func CircleRectIntersects(pos Vec2, radius float64, rect RectState) bool {
	effectiveRadius := math.Max(0, radius-collisionSkin)
	closestX := Clamp(pos.X, rect.X, rect.X+rect.W)
	closestY := Clamp(pos.Y, rect.Y, rect.Y+rect.H)
	dx := closestX - pos.X
	dy := closestY - pos.Y
	return dx*dx+dy*dy < effectiveRadius*effectiveRadius
}

func SegmentRectIntersects(start, end Vec2, rect RectState) bool {
	minX := math.Min(start.X, end.X)
	maxX := math.Max(start.X, end.X)
	minY := math.Min(start.Y, end.Y)
	maxY := math.Max(start.Y, end.Y)
	if maxX < rect.X || minX > rect.X+rect.W || maxY < rect.Y || minY > rect.Y+rect.H {
		return false
	}
	if rect.Contains(start) || rect.Contains(end) {
		return true
	}
	dx := end.X - start.X
	dy := end.Y - start.Y
	t0 := 0.0
	t1 := 1.0
	edges := [][2]float64{
		{-dx, start.X - rect.X},
		{dx, rect.X + rect.W - start.X},
		{-dy, start.Y - rect.Y},
		{dy, rect.Y + rect.H - start.Y},
	}
	for _, edge := range edges {
		p := edge[0]
		q := edge[1]
		if math.Abs(p) <= 0.000001 {
			if q < 0 {
				return false
			}
			continue
		}
		t := q / p
		if p < 0 {
			if t > t1 {
				return false
			}
			t0 = math.Max(t0, t)
		} else {
			if t < t0 {
				return false
			}
			t1 = math.Min(t1, t)
		}
	}
	return true
}

func ResolveCirclePenetration(pos Vec2, radius float64, walls []RectState) Vec2 {
	for i := 0; i < 4; i++ {
		moved := false
		for _, wall := range walls {
			push, ok := circleRectPush(pos, radius, wall)
			if !ok {
				continue
			}
			pos = pos.Add(push)
			moved = true
		}
		if !moved {
			return pos
		}
	}
	return pos
}

func moveAxis(pos Vec2, amount float64, axis string, radius float64, walls []RectState) Vec2 {
	if math.Abs(amount) <= 0.000001 {
		return pos
	}
	original := pos.X
	if axis == "y" {
		original = pos.Y
	}
	candidate := setAxis(pos, axis, original+amount)
	if !BlockedAt(candidate, radius, walls) {
		return candidate
	}
	low := 0.0
	high := 1.0
	for i := 0; i < 10; i++ {
		mid := (low + high) * 0.5
		candidate = setAxis(pos, axis, original+amount*mid)
		if BlockedAt(candidate, radius, walls) {
			high = mid
		} else {
			low = mid
		}
	}
	candidate = setAxis(pos, axis, original+amount*low)
	if BlockedAt(candidate, radius, walls) {
		return pos
	}
	return candidate
}

func setAxis(pos Vec2, axis string, value float64) Vec2 {
	if axis == "x" {
		pos.X = value
	} else {
		pos.Y = value
	}
	return pos
}

func circleRectPush(pos Vec2, radius float64, rect RectState) (Vec2, bool) {
	closestX := Clamp(pos.X, rect.X, rect.X+rect.W)
	closestY := Clamp(pos.Y, rect.Y, rect.Y+rect.H)
	dx := pos.X - closestX
	dy := pos.Y - closestY
	distanceSq := dx*dx + dy*dy
	if distanceSq >= radius*radius {
		return Vec2{}, false
	}
	if distanceSq > 0.000001 {
		distance := math.Sqrt(distanceSq)
		overlap := radius - distance + resolveEpsilon
		return Vec2{X: dx / distance * overlap, Y: dy / distance * overlap}, true
	}
	left := math.Abs(pos.X - rect.X)
	right := math.Abs(rect.X + rect.W - pos.X)
	top := math.Abs(pos.Y - rect.Y)
	bottom := math.Abs(rect.Y + rect.H - pos.Y)
	nearest := math.Min(math.Min(left, right), math.Min(top, bottom))
	switch nearest {
	case left:
		return Vec2{X: -(radius + left + resolveEpsilon)}, true
	case right:
		return Vec2{X: radius + right + resolveEpsilon}, true
	case top:
		return Vec2{Y: -(radius + top + resolveEpsilon)}, true
	default:
		return Vec2{Y: radius + bottom + resolveEpsilon}, true
	}
}
