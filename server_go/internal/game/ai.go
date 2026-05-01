package game

import (
	"math"
	"sync"

	"neonoutbreak/server_go/shared"
)

type AITask struct {
	Zombie     Zombie
	Players    []Player
	Walls      []shared.RectState
	Spec       shared.ZombieSpec
	Generation int64
	Now        float64
}

type AIDecision struct {
	ZombieID       string
	Generation     int64
	Mode           string
	TargetPlayerID string
	LastKnown      Vec2
	HasLastKnown   bool
	Alertness      float64
}

type AIWorkerPool struct {
	requests chan AITask
	results  chan AIDecision
	stop     chan struct{}
	wg       sync.WaitGroup
}

func NewAIWorkerPool(workers int) *AIWorkerPool {
	pool := &AIWorkerPool{
		requests: make(chan AITask, 2048),
		results:  make(chan AIDecision, 2048),
		stop:     make(chan struct{}),
	}
	for i := 0; i < workers; i++ {
		pool.wg.Add(1)
		go pool.worker()
	}
	return pool
}

func (p *AIWorkerPool) Close() {
	close(p.stop)
	p.wg.Wait()
}

func (p *AIWorkerPool) Submit(task AITask) bool {
	if p == nil {
		return false
	}
	select {
	case p.requests <- task:
		return true
	default:
		return false
	}
}

func (p *AIWorkerPool) Drain(maxResults int) []AIDecision {
	if p == nil {
		return nil
	}
	out := make([]AIDecision, 0, maxResults)
	for len(out) < maxResults {
		select {
		case result := <-p.results:
			out = append(out, result)
		default:
			return out
		}
	}
	return out
}

func (p *AIWorkerPool) worker() {
	defer p.wg.Done()
	for {
		select {
		case <-p.stop:
			return
		case task := <-p.requests:
			p.results <- decide(task)
		}
	}
}

func (w *World) drainAI() {
	for _, decision := range w.ai.Drain(256) {
		z := w.zombies[decision.ZombieID]
		if z == nil || z.Generation != decision.Generation {
			continue
		}
		if decision.Mode != "" {
			z.Mode = decision.Mode
			z.TargetPlayerID = decision.TargetPlayerID
			z.LastKnown = decision.LastKnown
			z.HasLastKnown = decision.HasLastKnown
			z.Alertness = decision.Alertness
			z.SearchTimer = 5
			z.HasWaypoint = false
		}
	}
}

func (w *World) scheduleAI() {
	if w.cfg.Mode == "pvp" || w.ai == nil {
		return
	}
	maxTasks := max(1, w.cfg.ZombieAIWorkers*4)
	scheduled := 0
	for _, z := range w.zombies {
		if scheduled >= maxTasks || w.worldTime < z.DecisionDue {
			continue
		}
		candidates, active := w.aiCandidates(z)
		interval := 1 / maxFloat(0.1, w.cfg.ZombieAIFarRate)
		if active {
			interval = 1 / maxFloat(0.25, w.cfg.ZombieAIDecisionRate)
		}
		z.DecisionDue = w.worldTime + interval*(0.75+w.rng.Float64()*0.6)
		if len(candidates) == 0 {
			continue
		}
		task := AITask{Zombie: *z, Players: candidates, Walls: w.closedWalls(z.Floor), Spec: w.zombieSpec(z.Kind), Generation: z.Generation, Now: w.worldTime}
		if w.ai.Submit(task) {
			scheduled++
		}
	}
}

func (w *World) aiCandidates(z *Zombie) ([]Player, bool) {
	active := z.Mode != "patrol"
	far := maxFloat(w.cfg.ZombieAIFarRadius, 3200)
	activeRadius := maxFloat(w.cfg.ZombieAIActiveRadius, 900)
	candidates := make([]Player, 0, 8)
	for _, p := range w.players {
		if !p.Alive || p.Floor != z.Floor {
			continue
		}
		dist := z.Pos.Distance(p.Pos)
		if dist <= far || (p.Noise > 0 && dist <= 700+p.Noise) || p.ID == z.TargetPlayerID {
			candidates = append(candidates, *clonePlayer(p))
			if dist <= activeRadius || p.Noise > 0 || p.ID == z.TargetPlayerID {
				active = true
			}
		}
		if len(candidates) >= 8 {
			break
		}
	}
	return candidates, active
}

func decide(task AITask) AIDecision {
	z := task.Zombie
	spec := task.Spec
	bestVisible := Player{}
	bestVisibleDist := math.MaxFloat64
	for _, p := range task.Players {
		dist := z.Pos.Distance(p.Pos)
		if p.Floor != z.Floor || dist > spec.SightRange || dist >= bestVisibleDist {
			continue
		}
		angle := z.Pos.AngleTo(p.Pos)
		if math.Abs(angleDelta(z.Facing, angle)) > spec.FOVDegrees*math.Pi/180*0.5 {
			continue
		}
		if aiLineBlocked(z.Pos, p.Pos, task.Walls, false) {
			continue
		}
		bestVisible = p
		bestVisibleDist = dist
	}
	if bestVisible.ID != "" {
		return AIDecision{
			ZombieID:       z.ID,
			Generation:     task.Generation,
			Mode:           "chase",
			TargetPlayerID: bestVisible.ID,
			LastKnown:      bestVisible.Pos,
			HasLastKnown:   true,
			Alertness:      1,
		}
	}
	if z.Mode == "chase" {
		return AIDecision{ZombieID: z.ID, Generation: task.Generation}
	}
	bestHeard := Player{}
	bestHeardDist := math.MaxFloat64
	for _, p := range task.Players {
		if p.Noise <= 0 || p.InsideBuilding != nil {
			continue
		}
		dist := z.Pos.Distance(p.Pos)
		if p.Floor == z.Floor && dist <= spec.HearingRange+p.Noise*spec.Sensitivity && dist < bestHeardDist && !aiLineBlocked(z.Pos, p.Pos, task.Walls, true) {
			bestHeard = p
			bestHeardDist = dist
		}
	}
	if bestHeard.ID != "" {
		return AIDecision{
			ZombieID:       z.ID,
			Generation:     task.Generation,
			Mode:           "investigate",
			TargetPlayerID: bestHeard.ID,
			LastKnown:      bestHeard.Pos,
			HasLastKnown:   true,
			Alertness:      0.8,
		}
	}
	return AIDecision{ZombieID: z.ID, Generation: task.Generation}
}

func aiLineBlocked(start Vec2, end Vec2, walls []shared.RectState, sound bool) bool {
	for _, wall := range walls {
		if shared.SegmentRectIntersects(start, end, wall) {
			if sound && wall.W < 28 && wall.H < 90 {
				continue
			}
			return true
		}
	}
	return false
}

func zombieSight(kind string) float64 {
	switch kind {
	case "runner":
		return 620
	case "brute":
		return 470
	case "leaper":
		return 660
	default:
		return 540
	}
}

func zombieHearing(kind string) float64 {
	switch kind {
	case "runner":
		return 620
	case "brute":
		return 360
	case "leaper":
		return 560
	default:
		return 430
	}
}

func zombieFOV(kind string) float64 {
	switch kind {
	case "runner":
		return 132 * math.Pi / 180
	case "brute":
		return 94 * math.Pi / 180
	case "leaper":
		return 124 * math.Pi / 180
	default:
		return 116 * math.Pi / 180
	}
}

func zombieSensitivity(kind string) float64 {
	switch kind {
	case "runner":
		return 1.25
	case "brute":
		return 0.65
	case "leaper":
		return 1.05
	default:
		return 0.85
	}
}

func angleDelta(a, b float64) float64 {
	return math.Mod(b-a+math.Pi, math.Pi*2) - math.Pi
}
