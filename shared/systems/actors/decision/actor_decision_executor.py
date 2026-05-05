from __future__ import annotations

from concurrent.futures import as_completed
from dataclasses import dataclass

from shared.systems.actors.decision.actor_decision_dto import ActorDecisionInput
from shared.systems.actors.decision.actor_decision_registry import ActorDecisionRegistry, ActorDecisionWorker
from shared.systems.actors.decision.actor_decision_result import ActorDecisionOutput


@dataclass(frozen=True, slots=True)
class ActorDecisionExecutionConfig:
    sync_actor_limit: int = 32
    thread_actor_limit: int = 96
    process_actor_limit: int = 192
    enable_threads: bool = True
    enable_processes: bool = True


class ActorDecisionExecutor:
    def __init__(
        self,
        registry: ActorDecisionRegistry,
        config: ActorDecisionExecutionConfig | None = None,
    ) -> None:
        self._registry = registry
        self._config = config or ActorDecisionExecutionConfig()

    def execute(self, inputs: list[ActorDecisionInput], ctx) -> list[ActorDecisionOutput]:
        if not inputs:
            return []

        workers = [self._registry.get(decision_input.actor_type) for decision_input in inputs]
        backend = self._select_backend(inputs, workers, ctx)

        if backend == "process":
            return self._execute_process(inputs, workers, ctx)

        if backend == "thread":
            return self._execute_thread(inputs, workers, ctx)

        return self._execute_sync(inputs, workers, ctx)

    def _select_backend(
        self,
        inputs: list[ActorDecisionInput],
        workers: list[ActorDecisionWorker],
        ctx,
    ) -> str:
        count = len(inputs)
        config = self._config

        if count <= config.sync_actor_limit:
            return "sync"

        process_ready = (
            config.enable_processes
            and count >= config.process_actor_limit
            and ctx.process_pool.enabled
            and all(worker.supports_processes for worker in workers)
        )
        if process_ready and any(decision_input.cpu_heavy for decision_input in inputs):
            return "process"

        thread_ready = (
            config.enable_threads
            and count >= config.sync_actor_limit
            and count <= config.thread_actor_limit
            and ctx.thread_pool.enabled
            and all(worker.supports_threads for worker in workers)
        )
        if thread_ready:
            return "thread"

        return "sync"

    def _execute_sync(
        self,
        inputs: list[ActorDecisionInput],
        workers: list[ActorDecisionWorker],
        ctx,
    ) -> list[ActorDecisionOutput]:
        return [
            worker.execute(decision_input, ctx)
            for decision_input, worker in zip(inputs, workers)
        ]

    def _execute_thread(
        self,
        inputs: list[ActorDecisionInput],
        workers: list[ActorDecisionWorker],
        ctx,
    ) -> list[ActorDecisionOutput]:
        executor = ctx.thread_pool.executor
        if executor is None:
            return self._execute_sync(inputs, workers, ctx)

        futures = {
            executor.submit(worker.execute, decision_input, ctx): index
            for index, (decision_input, worker) in enumerate(zip(inputs, workers))
        }
        results: list[ActorDecisionOutput | None] = [None] * len(futures)

        for future in as_completed(futures):
            results[futures[future]] = future.result()

        return [result for result in results if result is not None]

    def _execute_process(
        self,
        inputs: list[ActorDecisionInput],
        workers: list[ActorDecisionWorker],
        ctx,
    ) -> list[ActorDecisionOutput]:
        executor = ctx.process_pool.executor
        if executor is None:
            return self._execute_sync(inputs, workers, ctx)

        futures = {
            executor.submit(_execute_detached, worker, decision_input): index
            for index, (decision_input, worker) in enumerate(zip(inputs, workers))
        }
        results: list[ActorDecisionOutput | None] = [None] * len(futures)

        for future in as_completed(futures):
            results[futures[future]] = future.result()

        return [result for result in results if result is not None]


def _execute_detached(
    worker: ActorDecisionWorker,
    decision_input: ActorDecisionInput,
) -> ActorDecisionOutput:
    return worker.execute(decision_input, None)
