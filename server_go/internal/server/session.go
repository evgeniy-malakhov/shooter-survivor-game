package server

import (
	"net"
	"sync"
	"sync/atomic"
	"time"
)

type Session struct {
	PlayerID string
	Name     string
	Token    string
	Conn     net.Conn

	control  chan []byte
	snapshot chan []byte
	done     chan struct{}
	closed   atomic.Bool

	LastSeen          atomic.Int64
	LastInputSeq      atomic.Int64
	LastAckedInputSeq atomic.Int64
	LastSnapshotTick  atomic.Int64
	Sequence          atomic.Int64
	PingMS            atomic.Int64
	DroppedSnapshots  atomic.Uint64
	closeOnce         sync.Once
}

func NewSession(playerID, name, token string, conn net.Conn, queueSize int) *Session {
	if queueSize < 16 {
		queueSize = 128
	}
	s := &Session{
		PlayerID: playerID,
		Name:     name,
		Token:    token,
		Conn:     conn,
		control:  make(chan []byte, queueSize),
		snapshot: make(chan []byte, 1),
		done:     make(chan struct{}),
	}
	s.Touch()
	return s
}

func (s *Session) Touch() {
	s.LastSeen.Store(time.Now().UnixNano())
}

func (s *Session) EnqueueControl(packet []byte) bool {
	if s.closed.Load() {
		return false
	}
	select {
	case s.control <- packet:
		return true
	default:
		return false
	}
}

func (s *Session) ReplaceSnapshot(packet []byte) {
	if s.closed.Load() {
		return
	}
	select {
	case <-s.snapshot:
		s.DroppedSnapshots.Add(1)
	default:
	}
	select {
	case s.snapshot <- packet:
	default:
		s.DroppedSnapshots.Add(1)
	}
}

func (s *Session) Close() {
	s.closeOnce.Do(func() {
		s.closed.Store(true)
		close(s.done)
		_ = s.Conn.Close()
	})
}

type ResumeTicket struct {
	PlayerID     string
	Name         string
	Token        string
	ExpiresAt    time.Time
	LastInputSeq int64
	PingMS       int64
}
