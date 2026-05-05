class GameWorld:
    def __init__(self, config: WorldConfig) -> None:
        self.state = WorldStateFactory.create(config)
        self.ctx = WorldContextFactory.create(self.state, config)
        self.systems = SystemScheduler([
            PlayerSystem(),
            ProjectileSystem(),
            GrenadeSystem(),
            MineSystem(),
            PoisonSystem(),
            SoundSystem(),
            ZombieActorSystem(),
            SoldierActorSystem(),
            SpawnSystem(),
            LootSpawnSystem(),
        ])

    def update(self, dt: float) -> None:
        with self._lock:
            self.state.time += dt
            self.systems.update_all(self.state, self.ctx, dt)