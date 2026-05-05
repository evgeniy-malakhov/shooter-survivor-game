package server

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"strconv"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"neonoutbreak/server_go/internal/config"
	"neonoutbreak/server_go/internal/game"
	"neonoutbreak/server_go/internal/observability"
	"neonoutbreak/server_go/internal/protocol"
)

type Server struct {
	cfg         config.Config
	world       *game.World
	stats       *game.RuntimeStats
	telemetry   *observability.Registry
	probe       *observability.Probe
	probeCancel context.CancelFunc

	listener net.Listener
	mu       sync.RWMutex
	sessions map[string]*Session
	resume   map[string]ResumeTicket

	shutdown chan struct{}
	wg       sync.WaitGroup
}

func New(cfg config.Config) *Server {
	stats := &game.RuntimeStats{}
	s := &Server{
		cfg:       cfg,
		stats:     stats,
		telemetry: observability.NewRegistry(),
		world:     game.NewWorld(cfg, stats),
		sessions:  map[string]*Session{},
		resume:    map[string]ResumeTicket{},
		shutdown:  make(chan struct{}),
	}
	s.probe = observability.NewProbe(cfg.MetricsEnabled, cfg.MetricsHost, cfg.MetricsPort, s.telemetry, s.observabilitySnapshot)
	return s
}

func (s *Server) Run(ctx context.Context) error {
	addr := net.JoinHostPort(s.cfg.Host, strconv.Itoa(s.cfg.Port))
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		return err
	}
	s.listener = ln
	log.Printf("Go server listening on %s mode=%s tick=%d snapshot=%d", addr, s.cfg.Mode, s.cfg.TickRate, s.cfg.SnapshotRate)

	s.wg.Add(2)
	go s.simulationLoop()
	go s.snapshotLoop()
	if s.probe.Enabled() {
		probeCtx, cancel := context.WithCancel(context.Background())
		s.probeCancel = cancel
		s.wg.Add(1)
		go func() {
			defer s.wg.Done()
			if err := s.probe.Start(probeCtx); err != nil {
				log.Printf("observability probe disabled: %v", err)
			}
		}()
		log.Printf("observability probe listening on http://%s", s.probe.Addr())
	}

	go func() {
		<-ctx.Done()
		s.Shutdown()
	}()

	for {
		conn, err := ln.Accept()
		if err != nil {
			select {
			case <-s.shutdown:
				s.wg.Wait()
				return nil
			default:
			}
			if errors.Is(err, net.ErrClosed) {
				return nil
			}
			log.Printf("accept error: %v", err)
			continue
		}
		_ = conn.(*net.TCPConn).SetNoDelay(true)
		s.wg.Add(1)
		go s.handleConn(conn)
	}
}

func (s *Server) Shutdown() {
	select {
	case <-s.shutdown:
		return
	default:
		close(s.shutdown)
	}
	if s.listener != nil {
		_ = s.listener.Close()
	}
	if s.probeCancel != nil {
		s.probeCancel()
	}
	s.mu.RLock()
	for _, session := range s.sessions {
		session.Close()
	}
	s.mu.RUnlock()
	s.world.Close()
}

func (s *Server) handleConn(conn net.Conn) {
	defer s.wg.Done()
	reader := protocol.NewReader(conn)
	first, err := reader.Read()
	if err != nil {
		_ = conn.Close()
		return
	}
	switch protocol.String(first["type"], "") {
	case "ping":
		_ = s.writeMessage(conn, "pong", s.pingPayload(first))
		_ = conn.Close()
	case "hello":
		s.acceptPlayer(conn, reader, first)
	case "resume":
		s.resumePlayer(conn, reader, first)
	default:
		_ = s.writeMessage(conn, "error", protocol.Message{"message": "expected hello"})
		_ = conn.Close()
	}
}

func (s *Server) acceptPlayer(conn net.Conn, reader *protocol.Reader, msg protocol.Message) {
	if !s.handshakeOK(conn, msg) {
		return
	}
	s.mu.RLock()
	full := len(s.sessions) >= s.cfg.MaxClients
	s.mu.RUnlock()
	if full {
		_ = s.writeMessage(conn, "error", protocol.Message{"message": "server is full"})
		_ = conn.Close()
		return
	}
	name := protocol.String(msg["name"], "Player")
	player := s.world.AddPlayer(name, "")
	token := newToken()
	session := NewSession(player.ID, player.Name, token, conn, s.cfg.OutputQueuePackets)
	s.mu.Lock()
	s.sessions[player.ID] = session
	delete(s.resume, player.ID)
	atomic.StoreInt64(&s.stats.ConnectedPlayers, int64(len(s.sessions)))
	s.mu.Unlock()

	s.wg.Add(2)
	go s.writer(session)
	go s.reader(session, reader)
	s.sendWelcome(session, false)
	log.Printf("player connected: %s (%s)", player.Name, player.ID)
}

func (s *Server) resumePlayer(conn net.Conn, reader *protocol.Reader, msg protocol.Message) {
	if !s.handshakeOK(conn, msg) {
		return
	}
	playerID := protocol.String(msg["player_id"], "")
	token := protocol.String(msg["session_token"], "")
	s.mu.Lock()
	ticket, ok := s.resume[playerID]
	if !ok || ticket.Token != token || time.Now().After(ticket.ExpiresAt) || !s.world.PlayerExists(playerID) {
		s.mu.Unlock()
		_ = s.writeMessage(conn, "error", protocol.Message{"message": "resume expired"})
		_ = conn.Close()
		return
	}
	delete(s.resume, playerID)
	session := NewSession(playerID, ticket.Name, token, conn, s.cfg.OutputQueuePackets)
	session.LastInputSeq.Store(ticket.LastInputSeq)
	session.PingMS.Store(ticket.PingMS)
	s.sessions[playerID] = session
	atomic.StoreInt64(&s.stats.ConnectedPlayers, int64(len(s.sessions)))
	s.mu.Unlock()
	atomic.AddUint64(&s.stats.Reconnects, 1)
	s.wg.Add(2)
	go s.writer(session)
	go s.reader(session, reader)
	s.sendWelcome(session, true)
	log.Printf("player resumed: %s (%s)", ticket.Name, playerID)
}

func (s *Server) handshakeOK(conn net.Conn, msg protocol.Message) bool {
	if protocol.Int(msg["protocol_version"], protocol.ProtocolVersion) != protocol.ProtocolVersion {
		_ = s.writeMessage(conn, "error", protocol.Message{"message": "unsupported protocol version"})
		_ = conn.Close()
		return false
	}
	if protocol.String(msg["snapshot_schema"], protocol.SnapshotSchema) != protocol.SnapshotSchema {
		_ = s.writeMessage(conn, "error", protocol.Message{"message": "unsupported snapshot schema"})
		_ = conn.Close()
		return false
	}
	return true
}

func (s *Server) reader(session *Session, reader *protocol.Reader) {
	defer s.wg.Done()
	defer s.disconnect(session)
	for {
		msg, err := reader.Read()
		if err != nil {
			return
		}
		atomic.AddUint64(&s.stats.BytesIn, uint64(estimateMessageSize(msg)))
		session.Touch()
		switch protocol.String(msg["type"], "") {
		case "input":
			seq := int64(protocol.Int(msg["seq"], 0))
			if seq <= session.LastInputSeq.Load() {
				continue
			}
			session.LastInputSeq.Store(seq)
			command, _ := msg["command"].(map[string]any)
			input := game.Input{
				Seq:      seq,
				PlayerID: session.PlayerID,
				MoveX:    protocol.Float(command["move_x"], 0),
				MoveY:    protocol.Float(command["move_y"], 0),
				AimX:     protocol.Float(command["aim_x"], 0),
				AimY:     protocol.Float(command["aim_y"], 0),
				Shooting: protocol.Bool(command["shooting"], false),
				Sprint:   protocol.Bool(command["sprint"], false),
				Sneak:    protocol.Bool(command["sneak"], false),
			}
			s.world.QueueInput(input)
			session.LastAckedInputSeq.Store(seq)
		case "command":
			receivedAt := time.Now()
			payload, _ := msg["payload"].(map[string]any)
			cmd := game.Command{
				PlayerID:  session.PlayerID,
				CommandID: int64(protocol.Int(msg["command_id"], 0)),
				Kind:      protocol.String(msg["kind"], ""),
				Payload:   payload,
				ResultFunc: func(result game.CommandResult) {
					s.telemetry.ObserveCommandAck(time.Since(receivedAt))
					s.sendControl(session, "command_result", protocol.Message{
						"command_id":  result.CommandID,
						"kind":        result.Kind,
						"ok":          result.OK,
						"reason":      result.Reason,
						"server_tick": result.ServerTick,
					})
					if !result.OK {
						atomic.AddUint64(&s.stats.CommandsRejected, 1)
					}
				},
			}
			if cmd.CommandID <= 0 || cmd.Kind == "" {
				cmd.ResultFunc(game.CommandResult{PlayerID: session.PlayerID, CommandID: cmd.CommandID, Kind: cmd.Kind, OK: false, Reason: "invalid_command"})
			} else {
				s.world.QueueCommand(cmd)
			}
		case "profile":
			name := protocol.String(msg["name"], session.Name)
			session.Name = name
			s.world.RenamePlayer(session.PlayerID, name)
		case "ping":
			session.PingMS.Store(int64(protocol.Float(msg["client_ping_ms"], 0)))
			s.sendControl(session, "pong", s.pingPayload(msg))
		case "state_hash":
			s.sendControl(session, "state_hash_result", protocol.Message{"ok": true, "tick": msg["tick"]})
		}
	}
}

func (s *Server) writer(session *Session) {
	defer s.wg.Done()
	for {
		select {
		case <-session.done:
			return
		default:
		}
		select {
		case packet := <-session.control:
			_, err := session.Conn.Write(packet)
			if err != nil {
				session.Close()
				return
			}
			atomic.AddUint64(&s.stats.BytesOut, uint64(len(packet)))
		default:
			select {
			case packet := <-session.control:
				_, err := session.Conn.Write(packet)
				if err != nil {
					session.Close()
					return
				}
				atomic.AddUint64(&s.stats.BytesOut, uint64(len(packet)))
			case packet := <-session.snapshot:
				_, err := session.Conn.Write(packet)
				if err != nil {
					session.Close()
					return
				}
				atomic.AddUint64(&s.stats.BytesOut, uint64(len(packet)))
			case <-session.done:
				return
			}
		}
	}
}

func (s *Server) disconnect(session *Session) {
	session.Close()
	s.mu.Lock()
	if s.sessions[session.PlayerID] == session {
		delete(s.sessions, session.PlayerID)
		s.resume[session.PlayerID] = ResumeTicket{
			PlayerID:     session.PlayerID,
			Name:         session.Name,
			Token:        session.Token,
			ExpiresAt:    time.Now().Add(time.Duration(s.cfg.ResumeTimeoutSeconds * float64(time.Second))),
			LastInputSeq: session.LastInputSeq.Load(),
			PingMS:       session.PingMS.Load(),
		}
	}
	atomic.StoreInt64(&s.stats.ConnectedPlayers, int64(len(s.sessions)))
	s.mu.Unlock()
	s.world.RemovePlayerInput(session.PlayerID)
}

func (s *Server) simulationLoop() {
	defer s.wg.Done()
	ticker := time.NewTicker(time.Second / time.Duration(s.cfg.TickRate))
	defer ticker.Stop()
	dt := 1.0 / float64(s.cfg.TickRate)
	for {
		select {
		case <-ticker.C:
			start := time.Now()
			s.world.Tick(dt)
			s.telemetry.ObserveTick(time.Since(start))
			s.cleanupResumeTickets()
		case <-s.shutdown:
			return
		}
	}
}

func (s *Server) snapshotLoop() {
	defer s.wg.Done()
	ticker := time.NewTicker(time.Second / time.Duration(s.cfg.SnapshotRate))
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			start := time.Now()
			snapshot := s.world.Snapshot()
			s.broadcastSnapshot(snapshot)
			duration := time.Since(start)
			s.stats.SnapshotMS = float64(duration.Microseconds()) / 1000
			s.telemetry.ObserveSnapshot(duration)
		case <-s.shutdown:
			return
		}
	}
}

func (s *Server) broadcastSnapshot(snapshot game.Snapshot) {
	s.mu.RLock()
	sessions := make([]*Session, 0, len(s.sessions))
	for _, session := range s.sessions {
		sessions = append(sessions, session)
	}
	s.mu.RUnlock()
	for _, session := range sessions {
		session.Sequence.Add(1)
		payload := protocol.Message{
			"tick":              snapshot.Tick,
			"seq":               session.Sequence.Load(),
			"ack_input_seq":     session.LastAckedInputSeq.Load(),
			"server_time":       snapshot.Time,
			"snapshot_interval": 1.0 / float64(s.cfg.SnapshotRate),
			"full":              true,
			"schema":            protocol.SnapshotSchema,
			"snapshot":          game.CompactSnapshot(snapshot, session.PlayerID, s.cfg.InterestRadius),
		}
		packet, err := protocol.Encode("snapshot", payload)
		if err != nil {
			continue
		}
		session.LastSnapshotTick.Store(snapshot.Tick)
		session.ReplaceSnapshot(packet)
		atomic.AddUint64(&s.stats.DroppedSnapshots, session.DroppedSnapshots.Swap(0))
	}
}

func (s *Server) sendWelcome(session *Session, resumed bool) {
	snapshot := s.world.Snapshot()
	payload := protocol.Message{
		"player_id":                session.PlayerID,
		"session_token":            session.Token,
		"resume_timeout":           s.cfg.ResumeTimeoutSeconds,
		"snapshot":                 game.CompactSnapshot(snapshot, session.PlayerID, s.cfg.InterestRadius),
		"schema":                   protocol.SnapshotSchema,
		"tick":                     snapshot.Tick,
		"seq":                      0,
		"ack_input_seq":            session.LastAckedInputSeq.Load(),
		"server_time":              snapshot.Time,
		"snapshot_interval":        1.0 / float64(s.cfg.SnapshotRate),
		"codec":                    "json",
		"protocol_version":         protocol.ProtocolVersion,
		"snapshot_schema":          protocol.SnapshotSchema,
		"server_version":           protocol.ServerVersion,
		"server_features":          protocol.ServerFeatures,
		"mode":                     s.cfg.Mode,
		"pvp":                      s.cfg.Mode == "pvp",
		"interest_radius":          s.cfg.InterestRadius,
		"building_interest_radius": s.cfg.InterestRadius,
		"resumed":                  resumed,
	}
	s.sendControl(session, "welcome", payload)
}

func (s *Server) sendControl(session *Session, typ string, payload protocol.Message) {
	packet, err := protocol.Encode(typ, payload)
	if err != nil {
		return
	}
	if !session.EnqueueControl(packet) {
		session.Close()
	}
}

func (s *Server) writeMessage(conn net.Conn, typ string, payload protocol.Message) error {
	packet, err := protocol.Encode(typ, payload)
	if err != nil {
		return err
	}
	_, err = conn.Write(packet)
	if err == nil {
		atomic.AddUint64(&s.stats.BytesOut, uint64(len(packet)))
	}
	return err
}

func (s *Server) pingPayload(msg protocol.Message) protocol.Message {
	metricsURL := ""
	if s.probe.Enabled() {
		metricsURL = fmt.Sprintf("http://%s/metrics", s.probe.Addr())
	}
	return protocol.Message{
		"sent":                     msg["sent"],
		"players":                  len(s.sessions),
		"max_players":              s.cfg.MaxClients,
		"ready":                    true,
		"zombies":                  atomic.LoadInt64(&s.stats.Zombies),
		"difficulty":               s.cfg.Difficulty,
		"mode":                     s.cfg.Mode,
		"pvp":                      s.cfg.Mode == "pvp",
		"interest_radius":          s.cfg.InterestRadius,
		"building_interest_radius": s.cfg.InterestRadius,
		"tick_ms":                  s.stats.TickMS,
		"tick_rate":                s.cfg.TickRate,
		"snapshot_rate":            s.cfg.SnapshotRate,
		"effective_snapshot_rate":  s.cfg.SnapshotRate,
		"codec":                    "json",
		"protocol":                 "tcp-frame-go-v1",
		"protocol_version":         protocol.ProtocolVersion,
		"snapshot_schema":          protocol.SnapshotSchema,
		"server_version":           protocol.ServerVersion,
		"server_features":          protocol.ServerFeatures,
		"resume_timeout":           s.cfg.ResumeTimeoutSeconds,
		"metrics_url":              metricsURL,
	}
}

func (s *Server) cleanupResumeTickets() {
	now := time.Now()
	s.mu.Lock()
	for playerID, ticket := range s.resume {
		if now.After(ticket.ExpiresAt) {
			delete(s.resume, playerID)
			s.world.RemovePlayer(playerID)
		}
	}
	s.mu.Unlock()
}

func (s *Server) observabilitySnapshot() observability.RuntimeSnapshot {
	s.mu.RLock()
	connected := int64(len(s.sessions))
	resumeTickets := int64(len(s.resume))
	s.mu.RUnlock()
	shuttingDown := s.isShuttingDown()
	return observability.RuntimeSnapshot{
		Ready:            !shuttingDown,
		AcceptingPlayers: !shuttingDown && connected < int64(s.cfg.MaxClients),
		Mode:             s.cfg.Mode,
		MaxPlayers:       s.cfg.MaxClients,
		TickRate:         s.cfg.TickRate,
		SnapshotRate:     s.cfg.SnapshotRate,
		ConnectedPlayers: connected,
		WorldPlayers:     atomic.LoadInt64(&s.stats.TotalPlayers),
		ResumeTickets:    resumeTickets,
		Zombies:          atomic.LoadInt64(&s.stats.Zombies),
		BytesSent:        atomic.LoadUint64(&s.stats.BytesOut),
		BytesReceived:    atomic.LoadUint64(&s.stats.BytesIn),
		DroppedSnapshots: atomic.LoadUint64(&s.stats.DroppedSnapshots),
		CommandsRejected: atomic.LoadUint64(&s.stats.CommandsRejected),
		Reconnects:       atomic.LoadUint64(&s.stats.Reconnects),
		UptimeSeconds:    time.Since(s.telemetry.StartedAt()).Seconds(),
	}
}

func (s *Server) isShuttingDown() bool {
	select {
	case <-s.shutdown:
		return true
	default:
		return false
	}
}

func RunWithSignals(cfg config.Config) error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	return New(cfg).Run(ctx)
}

func newToken() string {
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return strconv.FormatInt(time.Now().UnixNano(), 36)
	}
	return base64.RawURLEncoding.EncodeToString(raw)
}

func estimateMessageSize(msg protocol.Message) int {
	size := 16
	for k, v := range msg {
		size += len(k) + len(fmt.Sprint(v))
	}
	return size
}
