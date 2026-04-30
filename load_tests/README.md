# Server Load Testing

This folder contains a fake-client load runner for the authoritative online server. It is intentionally separate from the Pygame client so tests can run headless and scale to hundreds of TCP clients in one process.

## What It Simulates

Each fake client performs:

- versioned `hello` and `resume` handshakes;
- frequent movement/aim/shooting input;
- reliable commands such as `pickup`, `interact`, `select_slot`, `reload`, `inventory_action`, `toggle_utility` and `respawn`;
- random disconnect/reconnect using `session_token`;
- simulated client-side packet delay and jitter;
- optional local input frame drops.

## Metrics

The runner reports:

- server tick p95/p99 from periodic `pong.tick_ms`;
- snapshot arrival p95/p99;
- command acknowledgement p95/p99;
- inbound/outbound bytes per second;
- estimated dropped snapshots from snapshot sequence gaps;
- reconnect attempts, successes and success rate;
- command rejects/timeouts;
- server RAM/CPU when `psutil` can sample `--server-pid` or `--server-cmd`.

`psutil` is listed in the root `requirements.txt`. If it is not installed, the load test still runs, but CPU/RAM metrics are reported as unavailable.

## Profiles

`profiles.json` defines ready-to-run profiles:

- `smoke`: 10 clients for a quick validation.
- `50`: 50 clients.
- `100`: 100 clients.
- `300`: 300 clients.
- `500`: 500 clients.

Every profile can be overridden from the command line.

## Run Against An Existing Server

Start the server:

```powershell
python -m server.main --host 127.0.0.1 --port 8765 --difficulty medium --profile
```

In another terminal:

```powershell
python -m load_tests.fake_client_runner --profile smoke --host 127.0.0.1 --port 8765
```

Run 50 clients:

```powershell
python -m load_tests.fake_client_runner --profile 50 --host 127.0.0.1 --port 8765
```

Run 500 clients and export JSON:

```powershell
python -m load_tests.fake_client_runner --profile 500 --json-out load_tests/results/500.json
```

## Run And Monitor A Server PID

If the server is already running and you know its PID:

```powershell
python -m load_tests.fake_client_runner --profile 100 --server-pid 12345
```

This enables CPU/RAM sampling for that process when `psutil` is installed.

## Let The Runner Start The Server

The runner can start the server, wait until the TCP port is open, run the load test, then terminate the process:

```powershell
python -m load_tests.fake_client_runner `
  --profile 50 `
  --server-cmd "python -m server.main --host 127.0.0.1 --port 8765 --difficulty medium --profile"
```

This is convenient for repeatable local testing. For production-like graceful shutdown checks, start the server yourself and stop it with SIGTERM/SIGINT from your process manager.

## Useful Overrides

```powershell
python -m load_tests.fake_client_runner `
  --profile 100 `
  --duration 180 `
  --ramp-up 45 `
  --input-hz 20 `
  --command-rate 10 `
  --disconnect-rate 0.2 `
  --packet-delay-ms 40 `
  --packet-jitter-ms 120 `
  --input-drop-percent 2 `
  --json-out load_tests/results/custom.json
```

## How To Read Results

Good first indicators:

- `command ack ms p95/p99`: if this spikes, reliable command processing or client queues are overloaded.
- `snapshot interval ms p95/p99`: should stay close to the server snapshot interval under load.
- `estimated_dropped_snapshots`: some drops are acceptable for slow clients, but a fast rise means queue pressure or bandwidth saturation.
- `reconnect_success_rate`: should stay close to 100% while reconnect happens within `configs/server.json -> network.resume_timeout_seconds`.
- `server CPU %` and `server RSS MB`: use these to choose the next optimization target.

Recommended progression:

1. Run `smoke` after protocol changes.
2. Run `50` and `100` for everyday regression checks.
3. Run `300` before tuning interest management or AI cost.
4. Run `500` before changing transport or snapshot schema.
