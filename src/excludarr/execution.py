"""Shared mutation boundaries for manual commands and the daemon worker."""

from contextlib import nullcontext

from excludarr.locking import execution_lock


def execute_rules(ctx, *, dry_run: bool, on_acquired=None, **kwargs):
    from excludarr.engine import run

    with nullcontext() if dry_run else execution_lock(str(ctx.repo._engine.url)):
        if on_acquired:
            on_acquired()
        return run(ctx, dry_run=dry_run, **kwargs)


def execute_feed(config, slug, repo, now, *, publish=True, on_acquired=None):
    from excludarr.lists.service import refresh_list

    with execution_lock(str(repo._engine.url)) if publish else nullcontext():
        if on_acquired:
            on_acquired()
        return refresh_list(config, slug, repo, now, publish=publish)
