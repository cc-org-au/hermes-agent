from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time
import traceback

from cli import HermesCLI, _run_cleanup

AUTORESEARCH_UNBOUNDED_ITERATIONS_ENV = "HERMES_AUTORESEARCH_UNBOUNDED_ITERATIONS"
AUTORESEARCH_WALL_SECONDS_ENV = "HERMES_AUTORESEARCH_WALL_SECONDS"


def _emit(message: str) -> None:
    print(message, flush=True)


def _compact_text(text: str, limit: int = 520) -> str:
    """Wide default so the job log file stays detailed; TUI/gateway use digests separately."""
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3]}..."


def run_autoresearch_prompt_file(prompt_file: str) -> int:
    prompt_path = Path(prompt_file).expanduser().resolve()
    if not prompt_path.exists():
        _emit(f"[autoresearch][error] Prompt file not found: {prompt_path}")
        return 1

    prompt = prompt_path.read_text(encoding="utf-8")
    if not prompt.strip():
        _emit(f"[autoresearch][error] Prompt file is empty: {prompt_path}")
        return 1

    job_id = prompt_path.parent.name
    _emit(f"[autoresearch] Starting background run: {job_id}")
    _emit(f"[autoresearch] Prompt file: {prompt_path}")
    os.environ[AUTORESEARCH_UNBOUNDED_ITERATIONS_ENV] = "1"

    cli = HermesCLI(compact=True, max_turns=0)
    cli.tool_progress_mode = "all"
    cli.verbose = False

    try:
        if not cli._ensure_runtime_credentials():
            _emit("[autoresearch][error] Runtime credentials are not available.")
            return 1

        turn_route = cli._resolve_turn_agent_config(prompt)
        if turn_route["signature"] != cli._active_agent_route_signature:
            cli.agent = None

        if (
            cli.agent is not None
            and turn_route.get("skip_per_turn_tier_routing")
            and not cli._cli_agent_matches_turn_route(cli.agent, turn_route)
        ):
            cli.agent = None

        if not cli._init_agent(
            model_override=turn_route["model"],
            runtime_override=turn_route["runtime"],
            route_label=turn_route["label"],
            skip_per_turn_tier_routing=bool(
                turn_route.get("skip_per_turn_tier_routing")
            ),
        ):
            _emit("[autoresearch][error] Failed to initialize the Hermes agent.")
            return 1

        if cli.agent is None:
            _emit("[autoresearch][error] Agent initialization returned no agent.")
            return 1

        cli._sync_agent_to_pipeline_turn_route(turn_route)
        cli.agent.quiet_mode = True

        def _status_callback(event_type: str, message: str) -> None:
            text = str(message or "").strip()
            if text:
                _emit(
                    f"[autoresearch][status:{event_type}] {_compact_text(text, limit=720)}"
                )

        def _tool_progress_callback(
            tool_name: str, preview: str, _args: object | None = None
        ) -> None:
            if tool_name == "_thinking":
                return
            text = _compact_text(preview, limit=720)
            if text:
                _emit(f"[autoresearch][tool:{tool_name}] {text}")
            else:
                _emit(f"[autoresearch][tool:{tool_name}] started")

        cli.agent.status_callback = _status_callback
        cli.agent.tool_progress_callback = _tool_progress_callback
        cli.agent.thinking_callback = lambda _text: None
        cli.agent._print_fn = lambda *args, **kwargs: print(*args, flush=True, **kwargs)

        _wall_raw = (os.environ.get(AUTORESEARCH_WALL_SECONDS_ENV) or "").strip()
        try:
            _wall_sec = max(1, int(_wall_raw)) if _wall_raw else 0
        except ValueError:
            _wall_sec = 0
        if _wall_sec <= 0:
            from hermes_cli.autoresearch_wall_clock import DEFAULT_OUTER_RUNTIME_SECONDS

            _wall_sec = DEFAULT_OUTER_RUNTIME_SECONDS
            _emit(
                f"[autoresearch][warn] Missing/invalid {AUTORESEARCH_WALL_SECONDS_ENV}; "
                f"using default outer runtime { _wall_sec // 60 } minutes."
            )
        cli.agent._wall_clock_deadline_monotonic = time.monotonic() + float(_wall_sec)
        _h = _wall_sec // 3600
        _m = (_wall_sec % 3600) // 60
        _s = _wall_sec % 60
        _emit(
            f"[autoresearch] Hard wall-clock budget: {_h}h {_m}m {_s}s "
            f"({AUTORESEARCH_WALL_SECONDS_ENV}={_wall_sec})"
        )

        _emit(f"[autoresearch] Session ID: {cli.session_id}")
        _emit("[autoresearch] Iteration cap override: unbounded for this autoresearch run.")
        _emit("[autoresearch] Agent run started.")

        # One run_conversation() call should iterate until the wall-clock stop, but some paths
        # (exceptions, edge returns) can end a segment early. Re-arm the deadline and start
        # another segment while monotonic time remains — same wall end, shared transcript.
        _wall_end_mono = time.monotonic() + float(_wall_sec)
        _seg_hist = None
        _seg_idx = 0
        _max_segments = 256
        result = {}
        while _seg_idx < _max_segments:
            if time.monotonic() >= _wall_end_mono:
                _emit("[autoresearch][warn] Wall-clock end reached; stopping outer segment loop.")
                if not result:
                    result = {
                        "final_response": None,
                        "failed": False,
                        "wall_clock_exhausted": True,
                    }
                break

            cli.agent._wall_clock_deadline_monotonic = _wall_end_mono
            cli.agent._wall_clock_budget_exhausted = False
            cli.agent._wall_clock_deadline_logged = False

            _user_seg = (
                prompt
                if _seg_idx == 0
                else (
                    "[Autoresearch — outer driver] The previous segment ended before the hard "
                    "wall-clock stop. Continue from program.md using the transcript you already "
                    "have; keep iterating (tools + cycles) until the wall-clock is exhausted or "
                    "you cannot make progress."
                )
            )
            try:
                result = cli.agent.run_conversation(
                    user_message=_user_seg,
                    conversation_history=_seg_hist,
                    task_id=job_id,
                )
            except BaseException:
                _emit(
                    "[autoresearch][error] run_conversation raised:\n"
                    + traceback.format_exc()
                )
                result = {
                    "final_response": None,
                    "failed": True,
                    "wall_clock_exhausted": False,
                }
                break

            if not isinstance(result, dict):
                result = {"final_response": str(result or "")}

            _seg_hist = result.get("messages")

            if result.get("wall_clock_exhausted"):
                break

            if time.monotonic() >= _wall_end_mono - 1:
                break

            if result.get("failed"):
                _emit("[autoresearch][warn] Segment marked failed; stopping outer loop.")
                break

            # Inner run returned without exhausting the wall — continue if time remains.
            if time.monotonic() >= _wall_end_mono - 2:
                break

            _seg_idx += 1
            _emit(
                f"[autoresearch] Starting outer segment {_seg_idx + 1} "
                f"(wall end not reached; transcript turns={len(_seg_hist or [])})."
            )

        response = (
            result.get("final_response", "")
            if isinstance(result, dict)
            else str(result or "")
        )
        failed = bool(isinstance(result, dict) and result.get("failed"))
        wall_ex = bool(isinstance(result, dict) and result.get("wall_clock_exhausted"))

        _emit("[autoresearch] Agent run finished.")
        if wall_ex:
            _emit("[autoresearch] Stop reason: wall-clock budget reached (outer runtime).")
        if response:
            _emit("[autoresearch][final] Final response follows.")
            print(response, flush=True)
        else:
            _emit("[autoresearch][final] No final response was produced.")

        if wall_ex:
            return 0
        return 1 if failed else 0
    finally:
        try:
            _run_cleanup()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an autoresearch prompt file in a background Hermes worker."
    )
    parser.add_argument(
        "--prompt-file",
        required=True,
        help="Path to a prompt file generated by the /autoresearch flow.",
    )
    args = parser.parse_args()
    return run_autoresearch_prompt_file(args.prompt_file)


if __name__ == "__main__":
    raise SystemExit(main())
