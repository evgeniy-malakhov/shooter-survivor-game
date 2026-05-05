package observability

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"strconv"
	"time"
)

type Probe struct {
	enabled  bool
	host     string
	port     int
	registry *Registry
	runtime  func() RuntimeSnapshot
	server   *http.Server
}

func NewProbe(enabled bool, host string, port int, registry *Registry, runtime func() RuntimeSnapshot) *Probe {
	return &Probe{
		enabled:  enabled,
		host:     host,
		port:     port,
		registry: registry,
		runtime:  runtime,
	}
}

func (p *Probe) Enabled() bool {
	return p != nil && p.enabled
}

func (p *Probe) Addr() string {
	if p == nil {
		return ""
	}
	return net.JoinHostPort(p.host, strconv.Itoa(p.port))
}

func (p *Probe) Start(ctx context.Context) error {
	if !p.Enabled() {
		return nil
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", p.health)
	mux.HandleFunc("/ready", p.ready)
	mux.HandleFunc("/metrics", p.metrics)
	p.server = &http.Server{
		Addr:              p.Addr(),
		Handler:           mux,
		ReadHeaderTimeout: 2 * time.Second,
	}
	errCh := make(chan error, 1)
	go func() {
		errCh <- p.server.ListenAndServe()
	}()
	select {
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		_ = p.server.Shutdown(shutdownCtx)
		err := <-errCh
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	case err := <-errCh:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	}
}

func (p *Probe) health(w http.ResponseWriter, _ *http.Request) {
	p.writeJSON(w, http.StatusOK, map[string]any{
		"ok":      true,
		"service": "neon-go-server",
	})
}

func (p *Probe) ready(w http.ResponseWriter, _ *http.Request) {
	snapshot := p.runtime()
	status := http.StatusOK
	if !snapshot.Ready {
		status = http.StatusServiceUnavailable
	}
	p.writeJSON(w, status, map[string]any{
		"ready":             snapshot.Ready,
		"accepting_players": snapshot.AcceptingPlayers,
		"players":           snapshot.ConnectedPlayers,
		"max_players":       snapshot.MaxPlayers,
		"resume_tickets":    snapshot.ResumeTickets,
		"zombies":           snapshot.Zombies,
		"mode":              snapshot.Mode,
		"tick_rate":         snapshot.TickRate,
		"snapshot_rate":     snapshot.SnapshotRate,
	})
}

func (p *Probe) metrics(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
	_, _ = fmt.Fprint(w, p.registry.Prometheus(p.runtime()))
}

func (p *Probe) writeJSON(w http.ResponseWriter, status int, payload map[string]any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
