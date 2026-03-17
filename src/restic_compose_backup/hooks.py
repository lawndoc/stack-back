"""Backup hooks — pre, post, error, and finally lifecycle hooks.

Hooks allow running user-defined commands before and after the backup process.
They follow try/catch/finally semantics:

- **pre**: runs before backup starts
- **post**: runs only if all pre hooks and the backup itself succeeded
- **error**: runs only if a hook or the backup failed
- **finally**: always runs, regardless of outcome

Hooks can be defined on the backup container (global) or on target containers
(per-service).  For **pre** hooks, backup-container hooks execute first
(setup).  For **post/error/finally** hooks, the order is reversed:
target-container hooks execute first, then backup-container hooks (teardown).

Label format::

    stack-back.hooks.<stage>.<N>.cmd        command string
    stack-back.hooks.<stage>.<N>.context    service name to exec into (optional)
    stack-back.hooks.<stage>.<N>.on-error   "abort" (default) | "continue"

When ``context`` is omitted, the hook runs in the container where the label
is defined: backup-container hooks run locally (``commands.run``), target-
container hooks run via ``docker exec`` into that target container.  An
explicit ``context`` overrides this and execs into the named service
regardless of where the label is defined.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from restic_compose_backup import commands

logger = logging.getLogger(__name__)

HOOK_STAGES = ("pre", "post", "error", "finally")
LABEL_PREFIX = "stack-back.hooks."
ON_ERROR_ABORT = "abort"
ON_ERROR_CONTINUE = "continue"


@dataclass
class Hook:
    """A single hook command to execute at a lifecycle stage."""

    stage: str
    order: int
    cmd: str
    # None → runs in the container where the label is defined
    context: Optional[str] = None
    on_error: str = ON_ERROR_ABORT
    source_container_id: Optional[str] = None  # set by collect_hooks()
    source_service_name: Optional[str] = None  # set by collect_hooks()


def parse_hooks_from_labels(labels: dict, stage: str) -> List[Hook]:
    """Parse hook definitions from container labels for a given stage.

    Labels follow the pattern::

        stack-back.hooks.<stage>.<N>.cmd
        stack-back.hooks.<stage>.<N>.context     (optional)
        stack-back.hooks.<stage>.<N>.on-error    (optional, default: abort)

    Returns hooks sorted by order number.  Entries without a ``cmd`` property
    are skipped with a warning.
    """
    prefix = f"{LABEL_PREFIX}{stage}."
    hook_data: dict[int, dict[str, str]] = {}

    for label, value in labels.items():
        if not label.startswith(prefix):
            continue

        # Extract "<N>.<property>" from the label suffix after the prefix
        label_suffix = label[len(prefix):]
        parts = label_suffix.split(".", 1)
        if len(parts) != 2:
            logger.warning(
                "Malformed hook label '%s', expected <N>.<property>", label
            )
            continue

        try:
            order_num = int(parts[0])
        except ValueError:
            logger.warning("Invalid hook order number in label '%s'", label)
            continue

        property_name = parts[1]
        if order_num not in hook_data:
            hook_data[order_num] = {}
        hook_data[order_num][property_name] = value

    hooks: List[Hook] = []
    for order_num in sorted(hook_data.keys()):
        data = hook_data[order_num]
        cmd = data.get("cmd")
        if not cmd:
            logger.warning("Hook %s.%d has no 'cmd', skipping", stage, order_num)
            continue

        on_error = data.get("on-error", ON_ERROR_ABORT)
        if on_error not in (ON_ERROR_ABORT, ON_ERROR_CONTINUE):
            logger.warning(
                "Invalid on-error value '%s' for hook %s.%d, defaulting to '%s'",
                on_error,
                stage,
                order_num,
                ON_ERROR_ABORT,
            )
            on_error = ON_ERROR_ABORT

        hooks.append(
            Hook(
                stage=stage,
                order=order_num,
                cmd=cmd,
                context=data.get("context"),
                on_error=on_error,
            )
        )

    return hooks


def collect_hooks(stage, backup_container, target_containers):
    """Collect all hooks for *stage* from the backup container and targets.

    For **pre** hooks the backup-container hooks run first (set up global
    state before per-service preparation).

    For **post / error / finally** hooks the order is reversed: target-
    container hooks run first, then backup-container hooks (tear down
    per-service state before global cleanup).  This gives symmetric
    setup / teardown semantics::

        pre:     backup-container → target containers   (setup)
        post:    target containers → backup-container   (teardown)
        error:   target containers → backup-container   (teardown)
        finally: target containers → backup-container   (teardown)

    Source container metadata (id, service name) is attached to every hook
    so that context-free hooks know where to execute.
    """
    backup_hooks: List[Hook] = []
    for hook in parse_hooks_from_labels(backup_container._labels, stage):
        hook.source_container_id = backup_container.id
        hook.source_service_name = backup_container.service_name
        backup_hooks.append(hook)

    target_hooks: List[Hook] = []
    for container in target_containers:
        for hook in parse_hooks_from_labels(container._labels, stage):
            hook.source_container_id = container.id
            hook.source_service_name = container.service_name
            target_hooks.append(hook)

    if stage == "pre":
        # Setup: global first, then per-service
        return backup_hooks + target_hooks
    else:
        # Teardown (post / error / finally): per-service first, then global
        return target_hooks + backup_hooks


def execute_hooks(hooks, containers):
    """Execute *hooks* in order, resolving each hook's target context.

    Returns ``True`` when every hook either succeeds (exit code 0) or
    fails with ``on_error="continue"``.  Returns ``False`` as soon as
    any hook fails with ``on_error="abort"`` (the default); remaining
    hooks in the list are skipped.

    An empty *hooks* list is always considered successful.
    """
    if not hooks:
        return True

    for hook in hooks:
        context_info = f" (context: {hook.context})" if hook.context else ""
        logger.info(
            "Running %s hook [%d]: %s%s",
            hook.stage,
            hook.order,
            hook.cmd,
            context_info,
        )

        try:
            exit_code = _execute_hook(hook, containers)
        except Exception as ex:
            logger.error("Hook execution error: %s", ex)
            exit_code = 1

        if exit_code != 0:
            if hook.on_error == ON_ERROR_ABORT:
                logger.error(
                    "Aborting: %s hook [%d] failed with exit code %d (on-error=%s)",
                    hook.stage,
                    hook.order,
                    exit_code,
                    ON_ERROR_ABORT,
                )
                return False
            else:
                logger.warning(
                    "Continuing despite %s hook [%d] failure, exit code %d (on-error=%s)",
                    hook.stage,
                    hook.order,
                    exit_code,
                    ON_ERROR_CONTINUE,
                )

    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _execute_hook(hook, containers):
    """Resolve target context and execute a single hook.

    Returns the command's exit code (0 = success).
    """
    this_container = containers.this_container

    if hook.context:
        # Explicit context — look up the named service
        target = containers.get_service(hook.context)

        # It may be the backup container itself
        if target is None and this_container.service_name == hook.context:
            return _run_local(hook.cmd)

        if target is None:
            logger.error(
                "Hook context container '%s' not found, failing hook: %s",
                hook.context,
                hook.cmd,
            )
            return 1

        return _run_in_container(target.id, hook.cmd)
    else:
        # No context — run in the source container
        if hook.source_container_id == this_container.id:
            return _run_local(hook.cmd)
        else:
            return _run_in_container(hook.source_container_id, hook.cmd)


def _run_local(cmd):
    """Run a hook command locally in the backup process container."""
    logger.debug("Running hook locally: %s", cmd)
    return commands.run(["sh", "-c", cmd])


def _run_in_container(container_id, cmd):
    """Run a hook command inside another container via docker exec."""
    logger.debug("Running hook in container %s: %s", container_id, cmd)
    return commands.docker_exec(container_id, ["sh", "-c", cmd])
