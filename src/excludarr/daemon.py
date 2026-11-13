"""One serial worker, independent HTTP serving and persistent job outcomes."""

import logging
import queue
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock, Thread
from time import monotonic
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from excludarr import reporting
from excludarr.config import ConfigError
from excludarr.diagnostics import safe_error
from excludarr.execution import execute_feed, execute_rules
from excludarr.facts import Clients, Context
from excludarr.jobs import JobKey, PendingJob, Planner, configured_jobs
from excludarr.lists.server import make_server
from excludarr.lists.service import fingerprint, snapshot_valid
from excludarr.locking import WorkBusy

log = logging.getLogger(__name__)


def utc_now():
    return datetime.now(UTC)


@dataclass
class BatchResult:
    completed: dict[JobKey, str] = field(default_factory=dict)
    unstarted: list[PendingJob] = field(default_factory=list)


def execute_batch(
    config, repo, instance, jobs, stop, now=utc_now, *, on_start=None, on_complete=None
):
    result = BatchResult()
    started, partial = {}, {}
    by_key = {job.key: job for job in jobs}
    acquired_at = None
    active = None

    def acquired():
        nonlocal acquired_at
        acquired_at = now()

    def start(key, at=None):
        nonlocal active
        started[key] = repo.job_start(instance, key, by_key[key].due, at or now())
        active = key
        if on_start:
            on_start(key)

    def finish(key, outcome, summary, error=None):
        at = now()
        repo.job_finish(instance, started[key], outcome, summary, error, at)
        result.completed[key] = outcome
        if on_complete:
            on_complete(key, at)

    def completed_rule(report):
        summary = reporting.run_document([report], dry_run=False)["summary"]
        summary["unknown"] = len(report.unknown)
        outcome = (
            "failed"
            if summary["failed"]
            else "warning"
            if summary["cleanup_warnings"] or summary["unknown"]
            else "success"
        )
        messages = list(report.warnings)
        for _, action in report.executed:
            if not action.ok:
                messages.append(action.detail)
            messages.extend(action.side_effect_errors)
        if report.unknown:
            messages.append(f"Required data unavailable for {len(report.unknown)} titles")
        error = safe_error(config, "; ".join(messages)) if messages else None
        finish(("rule", report.rule.name), outcome, summary, error)

    if stop.is_set():
        return BatchResult(unstarted=jobs)
    clients = None
    try:
        if jobs[0].key[0] == "list":
            key = jobs[0].key

            def feed_start():
                acquired()
                start(key)

            report = execute_feed(config, key[1], repo, now(), on_acquired=feed_start)
            warning = any(
                item.get("unknown") and item["decision"] == "excluded" for item in report["items"]
            )
            finish(key, "warning" if warning else "success", report["summary"])
        else:
            clients = Clients.from_config(config)
            ctx = Context(config, clients, repo, now())
            execute_rules(
                ctx,
                dry_run=False,
                rule_names=frozenset(key[1] for key in by_key),
                should_stop=stop.is_set,
                on_acquired=acquired,
                on_rule_start=lambda rule: start(("rule", rule.name)),
                on_report=lambda report: partial.update({("rule", report.rule.name): report}),
                on_rule_complete=completed_rule,
            )
    except WorkBusy:
        pass  # Keep the same due timestamp; a manual command currently owns execution.
    except SQLAlchemyError:
        raise
    except Exception as error:
        message = safe_error(config, error)
        log.warning("Scheduled execution failed: %s", message)
        if active is not None and active not in result.completed:
            report = partial.get(active)
            summary = reporting.run_document([report], dry_run=False)["summary"] if report else {}
            finish(active, "failed", summary, message)
        elif not started:
            # A shared preflight failure belongs to the whole due batch.
            for job in jobs:
                start(job.key, acquired_at)
                finish(job.key, "failed", {}, message)
        else:
            raise
    finally:
        if clients:
            clients.close()
    result.unstarted = [job for job in jobs if job.key not in result.completed]
    return result


def run_daemon(config, repo, *, host, port, stop, now=utc_now):
    jobs = configured_jobs(config)
    if not jobs and config.list_proxy is None:
        raise ConfigError("daemon needs scheduled jobs or configured list feeds")
    server = make_server(config, repo, host, port) if config.list_proxy is not None else None
    server_thread = worker = None
    instance = str(uuid4())
    initialized = False
    outcomes = queue.Queue()
    lock = RLock()
    last_snapshot = None
    fatal = None
    try:
        started_at = now()
        planner = Planner(jobs, config.scheduler.timezone, started_at, repo.job_watermarks())
        repo.scheduler_start(instance, jobs, config.scheduler.timezone, started_at)
        initialized = True
        for job in jobs:
            if job.key[0] == "list" and not snapshot_valid(
                repo.list_snapshot(job.key[1]), fingerprint(config, job.key[1]), started_at
            ):
                planner.bootstrap(job.key, started_at)

        def sync():
            nonlocal last_snapshot
            snapshot = planner.snapshot()
            if snapshot != last_snapshot:
                repo.scheduler_update(instance, snapshot)
                last_snapshot = snapshot

        def start(key):
            with lock:
                planner.start(key)
                sync()

        def complete(key, at):
            with lock:
                planner.complete(key, at)
                sync()

        def work(batch):
            try:
                outcomes.put(
                    execute_batch(
                        config,
                        repo,
                        instance,
                        batch,
                        stop,
                        now,
                        on_start=start,
                        on_complete=complete,
                    )
                )
            except Exception as error:  # noqa: BLE001 - propagate fatal worker/storage failures
                outcomes.put(error)
                stop.set()

        if server:
            server_thread = Thread(target=server.serve_forever, name="excludarr-http", daemon=True)
            server_thread.start()
        heartbeat_at = monotonic()
        while not stop.is_set():
            if worker is not None and not worker.is_alive():
                worker.join()
                outcome = outcomes.get_nowait()
                if isinstance(outcome, Exception):
                    raise outcome
                with lock:
                    planner.release(outcome.unstarted)
                worker = None
            with lock:
                planner.poll(now())
                batch = planner.take_batch(now()) if worker is None else []
                sync()
            if batch and not stop.is_set():
                worker = Thread(target=work, args=(batch,), name="excludarr-worker")
                worker.start()
            current = monotonic()
            if current - heartbeat_at >= 5:
                repo.scheduler_heartbeat(instance, now())
                heartbeat_at = current
            stop.wait(1)
    finally:
        stop.set()
        # Keep feeds and heartbeat available until in-flight work finishes.
        while worker is not None and worker.is_alive():
            worker.join(timeout=1)
            if initialized:
                try:
                    repo.scheduler_heartbeat(instance, now())
                except SQLAlchemyError as error:
                    fatal = error
        if worker is not None:
            worker.join()
            try:
                outcome = outcomes.get_nowait()
                if isinstance(outcome, Exception):
                    fatal = outcome
            except queue.Empty:
                pass
        if server:
            if server_thread:
                server.shutdown()
                server_thread.join()
            server.server_close()
        if initialized:
            try:
                repo.scheduler_stop(instance, now())
            except SQLAlchemyError as error:
                fatal = error
        if fatal:
            raise fatal
