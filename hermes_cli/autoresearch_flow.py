from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shlex
from typing import Any, Mapping, Optional
import uuid

from hermes_constants import get_hermes_home
from hermes_cli.integration_repos import resolve_autoresearch_repo


class AutoresearchFlowError(RuntimeError):
    """Raised when the autoresearch runtime flow cannot proceed."""


@dataclass(frozen=True)
class AutoresearchAppendResult:
    repo_path: Path
    program_path: Path


@dataclass(frozen=True)
class AutoresearchPreparedRun:
    repo_path: Path
    program_path: Path
    prompt_text: str
    job_id: str
    job_dir: Path
    prompt_path: Path
    log_path: Path


def _expand_path(path: Path) -> str:
    try:
        return str(path).replace(str(Path.home()), "~", 1)
    except Exception:
        return str(path)


def resolve_autoresearch_repo_path(config: Optional[Mapping[str, Any]] = None) -> Path:
    configured = resolve_autoresearch_repo(config)
    if configured:
        return Path(configured).expanduser()
    return get_hermes_home() / "skills" / "external-repos" / "autoresearch"


def resolve_autoresearch_program_path(config: Optional[Mapping[str, Any]] = None) -> Path:
    return resolve_autoresearch_repo_path(config) / "program.md"


def resolve_autoresearch_jobs_root() -> Path:
    return get_hermes_home() / "workspace" / "memory" / "runtime" / "autoresearch-jobs"


def resolve_hermes_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def format_autoresearch_capture_prompt(config: Optional[Mapping[str, Any]] = None) -> str:
    program_path = resolve_autoresearch_program_path(config)
    repo_path = resolve_autoresearch_repo_path(config)
    return "\n".join(
        [
            "Autoresearch is waiting for your run brief.",
            "",
            "Reply with your full instructions in your very next message.",
            "That next message is the only required interactive step.",
            "",
            "Include everything Hermes should use for this run:",
            "- your full program.md content or the exact additions you want appended",
            "- any preferred run tag, branch naming, total outer runtime, budget, model, or test constraints",
            "- any hard requirements about what Hermes must or must not change",
            "",
            "If you leave run-tag or branch details out, Hermes will choose deterministic defaults and will not ask again.",
            "If you leave total outer runtime out, Hermes will default to 30 minutes total for the overall autoresearch loop.",
            "",
            f"After that one reply, Hermes will append it to: {_expand_path(program_path)}",
            f"Autoresearch repo: {_expand_path(repo_path)}",
            "Then Hermes will launch the run in the background and continue without more setup questions.",
            "",
            "Use /autoresearch cancel to abort or /autoresearch show to print the repo/program paths again.",
        ]
    )


def format_autoresearch_target_message(config: Optional[Mapping[str, Any]] = None) -> str:
    repo_path = resolve_autoresearch_repo_path(config)
    program_path = resolve_autoresearch_program_path(config)
    return "\n".join(
        [
            f"Autoresearch repo: {_expand_path(repo_path)}",
            f"Program file: {_expand_path(program_path)}",
            "When ready, run /autoresearch and then send one complete follow-up message with all instructions.",
            "That follow-up message is the only required interactive step.",
            "If you omit total outer runtime, Hermes defaults to 30 minutes total for the outer loop.",
        ]
    )


def _build_managed_block(user_instructions: str) -> str:
    cleaned = (user_instructions or "").strip()
    if not cleaned:
        raise AutoresearchFlowError("No autoresearch instructions were provided.")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    return (
        f"<!-- HERMES_AUTORESEARCH_INSTRUCTIONS_START {timestamp} -->\n"
        f"## Hermes Runtime Instructions ({timestamp})\n\n"
        "The following instructions were provided through `/autoresearch`. "
        "Treat the newest Hermes Runtime Instructions block as the active run brief when it conflicts with older local addenda.\n\n"
        f"{cleaned}\n\n"
        "### Hermes Runtime Notes\n"
        "- Repository target: `efecanbasoz/autoresearch-cpu`\n"
        "- Prefer editing `train.py` unless the user explicitly asks for changes elsewhere.\n"
        "- Treat `prepare.py` as one-time data/tokenizer prep unless the user explicitly asks to change it.\n"
        "- If this block specifies a total outer runtime or wall-clock budget for the overall autoresearch loop, Hermes should treat it as a hard stop for the full run. If no outer runtime is specified, default to 30 minutes total for the outer loop rather than running indefinitely.\n"
        "- Hermes `/autoresearch` background workers bypass the normal Hermes max-iterations cap for this run; outer runtime is the stop condition instead.\n"
        "<!-- HERMES_AUTORESEARCH_INSTRUCTIONS_END -->\n"
    )


def _build_autoresearch_runtime_brief() -> str:
    return "\n".join(
        [
            "Read the repo's `program.md`, especially the newest `Hermes Runtime Instructions` block, and use it as the active run brief.",
            "Treat the user's just-submitted message as the only required interactive input for this run.",
            "Do not ask follow-up questions about run tags, branch tags, branch names, naming conventions, or similar setup trivia.",
            "If a run tag, branch name, artifact name, or similar identifier is needed, choose a deterministic default yourself and continue.",
            "If `program.md` or the newest Hermes Runtime Instructions block specifies a total outer runtime or wall-clock budget for the full autoresearch loop, treat that as a hard stop for the overall run.",
            "If no total outer runtime is specified, default to 30 minutes total for the overall autoresearch loop instead of running indefinitely.",
            "Keep the outer-loop runtime budget separate from any per-run `train.py` budget that the autoresearch repo already enforces.",
            "For Hermes `/autoresearch` background runs, bypass the normal Hermes max-iterations cap and let the outer runtime budget stop the run instead.",
            "Start the work immediately.",
            "When it is safe and useful, split the work into a small set of parallel delegated subprocesses for distinct workstreams.",
            "Continue autonomously until the run is complete or you hit a true hard blocker that only a human can resolve.",
            "Emit concise milestone-style progress updates and a final summary in normal output.",
        ]
    )


def _build_autoresearch_runtime_note(result: AutoresearchAppendResult) -> str:
    return " ".join(
        [
            f"The user's instructions were appended to `{_expand_path(result.program_path)}`.",
            f"The autoresearch repo for this Hermes profile is `{_expand_path(result.repo_path)}`.",
            "This is intended to run as a background-friendly autoresearch job.",
        ]
    )


def _build_autoresearch_skill_message(
    result: AutoresearchAppendResult,
    *,
    task_id: str | None = None,
) -> str:
    from agent.skill_commands import build_explicit_skill_invocation_message

    msg = build_explicit_skill_invocation_message(
        str(result.repo_path),
        _build_autoresearch_runtime_brief(),
        task_id=task_id,
        runtime_note=_build_autoresearch_runtime_note(result),
    )
    if not msg:
        raise AutoresearchFlowError(
            "Failed to load the installed autoresearch skill after updating program.md."
        )
    return msg


def _new_autoresearch_job_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"autoresearch_{timestamp}_{uuid.uuid4().hex[:6]}"


def prepare_autoresearch_background_run(
    *,
    user_instructions: str,
    task_id: str | None = None,
    config: Optional[Mapping[str, Any]] = None,
) -> AutoresearchPreparedRun:
    result = append_autoresearch_instructions(
        user_instructions=user_instructions,
        config=config,
    )
    prompt_text = _build_autoresearch_skill_message(result, task_id=task_id)

    job_id = _new_autoresearch_job_id()
    job_dir = resolve_autoresearch_jobs_root() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = job_dir / "prompt.txt"
    prompt_path.write_text(prompt_text, encoding="utf-8")
    log_path = job_dir / "run.log"

    return AutoresearchPreparedRun(
        repo_path=result.repo_path,
        program_path=result.program_path,
        prompt_text=prompt_text,
        job_id=job_id,
        job_dir=job_dir,
        prompt_path=prompt_path,
        log_path=log_path,
    )


def build_autoresearch_worker_command(
    prompt_path: Path,
    *,
    python_executable: str,
) -> str:
    return " ".join(
        [
            shlex.quote(python_executable),
            "-m",
            "hermes_cli.autoresearch_background",
            "--prompt-file",
            shlex.quote(str(prompt_path)),
        ]
    )


def append_autoresearch_instructions(
    user_instructions: str,
    config: Optional[Mapping[str, Any]] = None,
) -> AutoresearchAppendResult:
    repo_path = resolve_autoresearch_repo_path(config)
    program_path = resolve_autoresearch_program_path(config)

    if not repo_path.exists():
        raise AutoresearchFlowError(
            f"Autoresearch repo not found at `{_expand_path(repo_path)}`."
        )

    existing = ""
    if program_path.exists():
        existing = program_path.read_text(encoding="utf-8")
    else:
        program_path.parent.mkdir(parents=True, exist_ok=True)
        existing = "# autoresearch\n"

    block = _build_managed_block(user_instructions)
    prefix = existing.rstrip()
    new_text = f"{prefix}\n\n{block}" if prefix else block
    program_path.write_text(new_text, encoding="utf-8")
    return AutoresearchAppendResult(repo_path=repo_path, program_path=program_path)


def append_and_build_autoresearch_skill_message(
    *,
    user_instructions: str,
    task_id: str | None = None,
    config: Optional[Mapping[str, Any]] = None,
) -> tuple[AutoresearchAppendResult, str]:
    prepared = prepare_autoresearch_background_run(
        user_instructions=user_instructions,
        task_id=task_id,
        config=config,
    )
    return (
        AutoresearchAppendResult(
            repo_path=prepared.repo_path,
            program_path=prepared.program_path,
        ),
        prepared.prompt_text,
    )
