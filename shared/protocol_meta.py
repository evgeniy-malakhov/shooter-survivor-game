from __future__ import annotations


CLIENT_VERSION = "0.1.0"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = 2
CLIENT_FEATURES = [
    "commands",
    "input_ack",
    "client_prediction",
    "interpolation",
    "adaptive_snapshot",
    "resume_session",
    "state_hash",
    "health_probe",
]
SERVER_FEATURES = [
    "commands",
    "input_ack",
    "client_prediction",
    "interpolation",
    "adaptive_snapshot",
    "resume_session",
    "event_journal",
    "persistence_worker",
    "graceful_shutdown",
    "state_hash",
    "metrics_http",
    "health_probe",
    "configurable_tuning",
]
