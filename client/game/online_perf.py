from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OnlinePerfStats:
    snapshot_tick: int = -1
    snapshot_age_ms: float = 0.0
    snapshot_buffer_size: int = 0
    snapshot_interval_ms: float = 0.0
    ping_ms: float = 0.0
    pending_inputs: int = 0
    ack_input_seq: int = 0
    pending_commands: int = 0
    prediction_error_px: float = 0.0
    correction_px: float = 0.0
    network_state: str = "offline"
    decode_ms: float = 0.0
    interpolation_ms: float = 0.0
    prediction_ms: float = 0.0
    render_radius: float = 0.0
    server_interest_radius: float = 0.0
    minimap_radius: float = 0.0
    audio_radius: float = 0.0


