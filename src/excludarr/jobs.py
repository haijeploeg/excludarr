"""Scheduling identities, independent of storage and external integrations."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

JobKey = tuple[Literal["list", "rule"], str]


@dataclass(frozen=True)
class JobSpec:
    key: JobKey
    schedule: str
    order: int


def configured_jobs(config) -> list[JobSpec]:
    result = []
    if config.list_proxy:
        result.extend(
            JobSpec(("list", name), rule.schedule, index)
            for index, (name, rule) in enumerate(config.list_proxy.lists.items())
            if rule.schedule is not None
        )
    result.extend(
        JobSpec(("rule", rule.name), rule.schedule, index)
        for index, rule in enumerate(config.rules)
        if rule.enabled and rule.schedule is not None
    )
    return result


@dataclass(frozen=True)
class PendingJob:
    key: JobKey
    due: datetime


@dataclass
class _State:
    spec: JobSpec
    next_due: datetime | None
    last_dispatched_due: datetime | None = None
    pending_due: datetime | None = None
    reserved: bool = False
    running: bool = False


class Planner:
    def __init__(self, jobs, timezone, started_at, watermarks):
        from excludarr.scheduling import next_occurrence

        self.timezone = timezone
        self.states = {}
        for spec in jobs:
            watermark = watermarks.get(spec.key)
            base = max(started_at, watermark) if watermark else started_at
            self.states[spec.key] = _State(
                spec, next_occurrence(spec.schedule, base, timezone), watermark
            )

    def bootstrap(self, key, at):
        state = self.states[key]
        state.pending_due = min(at, state.pending_due) if state.pending_due else at

    def poll(self, now):
        for state in self.states.values():
            if not state.reserved and state.pending_due is None and state.next_due <= now:
                state.pending_due = state.next_due

    def take_batch(self, now):
        self.poll(now)
        waiting = [s for s in self.states.values() if s.pending_due is not None and not s.reserved]
        waiting.sort(key=lambda s: (s.pending_due, s.spec.key[0] != "list", s.spec.order))
        if not waiting:
            return []
        first = waiting[0]
        batch = (
            [first]
            if first.spec.key[0] == "list"
            else [
                state
                for state in waiting
                if state.spec.key[0] == "rule" and state.pending_due == first.pending_due
            ]
        )
        for state in batch:
            state.reserved = True
        return [PendingJob(state.spec.key, state.pending_due) for state in batch]

    def release(self, jobs):
        for job in jobs:
            state = self.states[job.key]
            state.reserved, state.running = False, False

    def start(self, key):
        state = self.states[key]
        state.running = True
        state.last_dispatched_due = max(
            state.pending_due, state.last_dispatched_due or state.pending_due
        )

    def complete(self, key, at):
        from excludarr.scheduling import next_occurrence

        state = self.states[key]
        due = max(state.pending_due, state.last_dispatched_due or state.pending_due)
        state.last_dispatched_due = due
        state.next_due = next_occurrence(state.spec.schedule, max(at, due), self.timezone)
        state.pending_due = None
        state.reserved, state.running = False, False

    def snapshot(self):
        return [
            {
                "kind": s.spec.key[0],
                "name": s.spec.key[1],
                "schedule": s.spec.schedule,
                "next_due": None if s.running else s.next_due,
                "pending_due": s.pending_due,
                "state": "running" if s.running else "pending" if s.pending_due else "idle",
                "last_dispatched_due": s.last_dispatched_due,
            }
            for s in self.states.values()
        ]
