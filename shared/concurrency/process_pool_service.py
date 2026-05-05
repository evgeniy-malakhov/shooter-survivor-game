from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor


class ProcessPoolService:
    def __init__(self, workers: int) -> None:
        self._executor: ProcessPoolExecutor | None = None

        if workers > 0:
            self._executor = ProcessPoolExecutor(max_workers=workers)

    @property
    def enabled(self) -> bool:
        return self._executor is not None

    @property
    def executor(self) -> ProcessPoolExecutor | None:
        return self._executor

    def close(self) -> None:
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None