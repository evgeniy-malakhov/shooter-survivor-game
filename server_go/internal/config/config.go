package config

import (
	"encoding/json"
	"errors"
	"os"
)

type Config struct {
	Host                 string  `json:"host"`
	Port                 int     `json:"port"`
	Mode                 string  `json:"mode"`
	Difficulty           string  `json:"difficulty"`
	MaxClients           int     `json:"max_clients"`
	TickRate             int     `json:"tick_rate"`
	SnapshotRate         int     `json:"snapshot_rate"`
	InterestRadius       float64 `json:"interest_radius"`
	MapWidth             float64 `json:"map_width"`
	MapHeight            float64 `json:"map_height"`
	InitialZombies       int     `json:"initial_zombies"`
	MaxZombies           int     `json:"max_zombies"`
	ZombieAIWorkers      int     `json:"zombie_ai_workers"`
	ZombieAIDecisionRate float64 `json:"zombie_ai_decision_rate"`
	ZombieAIFarRate      float64 `json:"zombie_ai_far_decision_rate"`
	ZombieAIActiveRadius float64 `json:"zombie_ai_active_radius"`
	ZombieAIFarRadius    float64 `json:"zombie_ai_far_radius"`
	OutputQueuePackets   int     `json:"output_queue_packets"`
	ResumeTimeoutSeconds float64 `json:"resume_timeout_seconds"`
	MetricsEnabled       bool    `json:"metrics_enabled"`
	MetricsHost          string  `json:"metrics_host"`
	MetricsPort          int     `json:"metrics_port"`
}

func Default() Config {
	return Config{
		Host:                 "127.0.0.1",
		Port:                 8767,
		Mode:                 "survival",
		Difficulty:           "medium",
		MaxClients:           50,
		TickRate:             30,
		SnapshotRate:         30,
		InterestRadius:       900,
		MapWidth:             28800,
		MapHeight:            19800,
		InitialZombies:       24,
		MaxZombies:           48,
		ZombieAIWorkers:      2,
		ZombieAIDecisionRate: 6,
		ZombieAIFarRate:      2,
		ZombieAIActiveRadius: 1800,
		ZombieAIFarRadius:    3200,
		OutputQueuePackets:   128,
		ResumeTimeoutSeconds: 30,
		MetricsEnabled:       true,
		MetricsHost:          "127.0.0.1",
		MetricsPort:          8776,
	}
}

func Load(path string) (Config, error) {
	cfg := Default()
	if path == "" {
		return cfg, nil
	}
	raw, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return cfg, nil
	}
	if err != nil {
		return cfg, err
	}
	if err := json.Unmarshal(raw, &cfg); err != nil {
		return cfg, err
	}
	cfg.Normalize()
	return cfg, nil
}

func (c *Config) Normalize() {
	if c.Host == "" {
		c.Host = "127.0.0.1"
	}
	if c.Port <= 0 {
		c.Port = 8767
	}
	if c.Mode != "pvp" {
		c.Mode = "survival"
	}
	if c.Difficulty == "" {
		c.Difficulty = "medium"
	}
	if c.MaxClients <= 0 {
		c.MaxClients = 50
	}
	if c.TickRate <= 0 {
		c.TickRate = 30
	}
	if c.SnapshotRate <= 0 {
		c.SnapshotRate = 30
	}
	if c.InterestRadius < 320 {
		c.InterestRadius = 900
	}
	if c.MapWidth <= 0 {
		c.MapWidth = 28800
	}
	if c.MapHeight <= 0 {
		c.MapHeight = 19800
	}
	if c.Mode == "pvp" {
		c.InitialZombies = 0
		c.MaxZombies = 0
		c.ZombieAIWorkers = 0
	}
	if c.OutputQueuePackets < 16 {
		c.OutputQueuePackets = 128
	}
	if c.ResumeTimeoutSeconds < 1 {
		c.ResumeTimeoutSeconds = 30
	}
	if c.MetricsHost == "" {
		c.MetricsHost = "127.0.0.1"
	}
	if c.MetricsPort <= 0 {
		c.MetricsPort = 8776
	}
}
