package observability

import (
	"fmt"
	"math"
	"runtime"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type RuntimeSnapshot struct {
	Ready            bool
	AcceptingPlayers bool
	Mode             string
	MaxPlayers       int
	TickRate         int
	SnapshotRate     int
	ConnectedPlayers int64
	WorldPlayers     int64
	ResumeTickets    int64
	Zombies          int64
	BytesSent        uint64
	BytesReceived    uint64
	DroppedSnapshots uint64
	CommandsRejected uint64
	Reconnects       uint64
	UptimeSeconds    float64
}

type Registry struct {
	startedAt  time.Time
	tick       *RollingSeries
	snapshot   *RollingSeries
	commandAck *RollingSeries
}

func NewRegistry() *Registry {
	return &Registry{
		startedAt:  time.Now(),
		tick:       NewRollingSeries(4096),
		snapshot:   NewRollingSeries(4096),
		commandAck: NewRollingSeries(4096),
	}
}

func (r *Registry) StartedAt() time.Time {
	return r.startedAt
}

func (r *Registry) ObserveTick(duration time.Duration) {
	r.tick.Observe(float64(duration.Microseconds()) / 1000.0)
}

func (r *Registry) ObserveSnapshot(duration time.Duration) {
	r.snapshot.Observe(float64(duration.Microseconds()) / 1000.0)
}

func (r *Registry) ObserveCommandAck(duration time.Duration) {
	r.commandAck.Observe(float64(duration.Microseconds()) / 1000.0)
}

func (r *Registry) Prometheus(runtimeSnapshot RuntimeSnapshot) string {
	var mem runtime.MemStats
	runtime.ReadMemStats(&mem)
	tick := r.tick.Summary()
	snapshot := r.snapshot.Summary()
	commandAck := r.commandAck.Summary()
	lines := []string{
		"# HELP neon_connected_players Currently connected players.",
		"# TYPE neon_connected_players gauge",
		fmt.Sprintf("neon_connected_players %d", runtimeSnapshot.ConnectedPlayers),
		"# HELP neon_world_players Players kept in the authoritative world, including resume windows.",
		"# TYPE neon_world_players gauge",
		fmt.Sprintf("neon_world_players %d", runtimeSnapshot.WorldPlayers),
		"# HELP neon_resume_tickets Players waiting in reconnect resume window.",
		"# TYPE neon_resume_tickets gauge",
		fmt.Sprintf("neon_resume_tickets %d", runtimeSnapshot.ResumeTickets),
		"# HELP neon_zombies Authoritative zombie count.",
		"# TYPE neon_zombies gauge",
		fmt.Sprintf("neon_zombies %d", runtimeSnapshot.Zombies),
		"# HELP neon_tick_ms Authoritative simulation tick duration in milliseconds.",
		"# TYPE neon_tick_ms summary",
		summaryLine("neon_tick_ms", "avg", tick.Avg),
		summaryLine("neon_tick_ms", "p95", tick.P95),
		summaryLine("neon_tick_ms", "p99", tick.P99),
		summaryLine("neon_tick_ms", "max", tick.Max),
		fmt.Sprintf("neon_tick_ms_count %d", tick.Count),
		"# HELP neon_snapshot_ms Snapshot collection/filtering/queue duration in milliseconds.",
		"# TYPE neon_snapshot_ms summary",
		summaryLine("neon_snapshot_ms", "avg", snapshot.Avg),
		summaryLine("neon_snapshot_ms", "p95", snapshot.P95),
		summaryLine("neon_snapshot_ms", "p99", snapshot.P99),
		summaryLine("neon_snapshot_ms", "max", snapshot.Max),
		fmt.Sprintf("neon_snapshot_ms_count %d", snapshot.Count),
		"# HELP neon_command_ack_ms Reliable command acknowledgement latency in milliseconds.",
		"# TYPE neon_command_ack_ms summary",
		summaryLine("neon_command_ack_ms", "avg", commandAck.Avg),
		summaryLine("neon_command_ack_ms", "p95", commandAck.P95),
		summaryLine("neon_command_ack_ms", "p99", commandAck.P99),
		summaryLine("neon_command_ack_ms", "max", commandAck.Max),
		fmt.Sprintf("neon_command_ack_ms_count %d", commandAck.Count),
		"# HELP neon_commands_rejected_total Reliable commands rejected by validation or queue limits.",
		"# TYPE neon_commands_rejected_total counter",
		fmt.Sprintf("neon_commands_rejected_total %d", runtimeSnapshot.CommandsRejected),
		"# HELP neon_reconnect_total Successful session resumes.",
		"# TYPE neon_reconnect_total counter",
		fmt.Sprintf("neon_reconnect_total %d", runtimeSnapshot.Reconnects),
		"# HELP neon_dropped_snapshots_total Realtime snapshots dropped/replaced because clients fell behind.",
		"# TYPE neon_dropped_snapshots_total counter",
		fmt.Sprintf("neon_dropped_snapshots_total %d", runtimeSnapshot.DroppedSnapshots),
		"# HELP neon_bytes_sent_total Bytes written to game clients.",
		"# TYPE neon_bytes_sent_total counter",
		fmt.Sprintf("neon_bytes_sent_total %d", runtimeSnapshot.BytesSent),
		"# HELP neon_bytes_received_total Approximate bytes received from game clients.",
		"# TYPE neon_bytes_received_total counter",
		fmt.Sprintf("neon_bytes_received_total %d", runtimeSnapshot.BytesReceived),
		"# HELP neon_ready Server readiness flag.",
		"# TYPE neon_ready gauge",
		fmt.Sprintf("neon_ready %d", boolFloat(runtimeSnapshot.Ready)),
		"# HELP neon_accepting_players Server accepts new player sessions.",
		"# TYPE neon_accepting_players gauge",
		fmt.Sprintf("neon_accepting_players %d", boolFloat(runtimeSnapshot.AcceptingPlayers)),
		"# HELP neon_uptime_seconds Process uptime in seconds.",
		"# TYPE neon_uptime_seconds counter",
		fmt.Sprintf("neon_uptime_seconds %.3f", runtimeSnapshot.UptimeSeconds),
		"# HELP neon_go_goroutines Current goroutine count.",
		"# TYPE neon_go_goroutines gauge",
		fmt.Sprintf("neon_go_goroutines %d", runtime.NumGoroutine()),
		"# HELP neon_go_heap_alloc_bytes Go heap bytes currently allocated.",
		"# TYPE neon_go_heap_alloc_bytes gauge",
		fmt.Sprintf("neon_go_heap_alloc_bytes %d", mem.HeapAlloc),
		"# HELP neon_go_heap_sys_bytes Go heap bytes reserved from OS.",
		"# TYPE neon_go_heap_sys_bytes gauge",
		fmt.Sprintf("neon_go_heap_sys_bytes %d", mem.HeapSys),
		"# HELP neon_go_gc_cycles_total Completed Go GC cycles.",
		"# TYPE neon_go_gc_cycles_total counter",
		fmt.Sprintf("neon_go_gc_cycles_total %d", mem.NumGC),
	}
	return strings.Join(lines, "\n") + "\n"
}

func summaryLine(name, label string, value float64) string {
	return fmt.Sprintf("%s_%s %.6f", name, label, value)
}

func boolFloat(value bool) int {
	if value {
		return 1
	}
	return 0
}

type Summary struct {
	Count int
	Avg   float64
	P95   float64
	P99   float64
	Max   float64
}

type RollingSeries struct {
	mu     sync.Mutex
	values []float64
	next   int
	full   bool
	count  atomic.Uint64
}

func NewRollingSeries(size int) *RollingSeries {
	if size < 32 {
		size = 32
	}
	return &RollingSeries{values: make([]float64, size)}
}

func (r *RollingSeries) Observe(value float64) {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return
	}
	r.mu.Lock()
	r.values[r.next] = value
	r.next = (r.next + 1) % len(r.values)
	if r.next == 0 {
		r.full = true
	}
	r.mu.Unlock()
	r.count.Add(1)
}

func (r *RollingSeries) Summary() Summary {
	r.mu.Lock()
	n := r.next
	if r.full {
		n = len(r.values)
	}
	sample := append([]float64(nil), r.values[:n]...)
	r.mu.Unlock()
	if len(sample) == 0 {
		return Summary{}
	}
	sort.Float64s(sample)
	total := 0.0
	for _, value := range sample {
		total += value
	}
	return Summary{
		Count: int(r.count.Load()),
		Avg:   total / float64(len(sample)),
		P95:   percentile(sample, 0.95),
		P99:   percentile(sample, 0.99),
		Max:   sample[len(sample)-1],
	}
}

func percentile(sorted []float64, p float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	index := int(math.Ceil(float64(len(sorted))*p)) - 1
	if index < 0 {
		index = 0
	}
	if index >= len(sorted) {
		index = len(sorted) - 1
	}
	return sorted[index]
}
