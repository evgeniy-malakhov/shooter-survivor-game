package main

import (
	"flag"
	"fmt"
	"log"
	"runtime"

	"neonoutbreak/server_go/internal/config"
	"neonoutbreak/server_go/internal/server"
)

func main() {
	var configPath string
	var host string
	var port int
	var mode string
	var difficulty string
	var tickRate int
	var snapshotRate int
	var zombieWorkers int
	var maxClients int

	flag.StringVar(&configPath, "config", "configs/server.json", "Path to server configuration JSON.")
	flag.StringVar(&host, "host", "", "Host/IP to bind. Overrides config.")
	flag.IntVar(&port, "port", 0, "TCP port to bind. Overrides config.")
	flag.StringVar(&mode, "mode", "", "Server mode: survival or pvp. Overrides config.")
	flag.StringVar(&difficulty, "difficulty", "", "Difficulty label advertised to clients.")
	flag.IntVar(&tickRate, "tick-rate", 0, "Authoritative simulation ticks per second.")
	flag.IntVar(&snapshotRate, "snapshot-rate", 0, "Snapshot send rate per second.")
	flag.IntVar(&zombieWorkers, "zombie-workers", -1, "Zombie AI worker goroutines. Use 0 to disable bot decisions.")
	flag.IntVar(&maxClients, "max-clients", 0, "Maximum connected clients.")
	flag.Parse()

	cfg, err := config.Load(configPath)
	if err != nil {
		log.Fatalf("load config: %v", err)
	}
	if host != "" {
		cfg.Host = host
	}
	if port > 0 {
		cfg.Port = port
	}
	if mode != "" {
		cfg.Mode = mode
	}
	if difficulty != "" {
		cfg.Difficulty = difficulty
	}
	if tickRate > 0 {
		cfg.TickRate = tickRate
	}
	if snapshotRate > 0 {
		cfg.SnapshotRate = snapshotRate
	}
	if zombieWorkers >= 0 {
		cfg.ZombieAIWorkers = zombieWorkers
	}
	if maxClients > 0 {
		cfg.MaxClients = maxClients
	}
	cfg.Normalize()

	fmt.Printf("Neon Outbreak Go server runtime=%s cpus=%d\n", runtime.Version(), runtime.NumCPU())
	if err := server.RunWithSignals(cfg); err != nil {
		log.Fatal(err)
	}
}
