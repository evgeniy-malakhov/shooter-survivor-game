from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ExecutorConfig:
    process_workers: int
    thread_workers: int


def build_executor_config(
    *,
    requested_process_workers: int | None,
    enable_process_pool: bool,
    enable_thread_pool: bool,
) -> ExecutorConfig:
    cpu_count = os.cpu_count() or 4
    cpu_budget = max(1, cpu_count - 1)

    process_workers = 0
    if enable_process_pool:
        process_workers = (
            min(4, cpu_budget)
            if requested_process_workers is None
            else max(0, int(requested_process_workers))
        )

    thread_workers = 0
    if enable_thread_pool:
        thread_workers = max(2, min(16, cpu_count * 2))

    return ExecutorConfig(
        process_workers=process_workers,
        thread_workers=thread_workers,
    )