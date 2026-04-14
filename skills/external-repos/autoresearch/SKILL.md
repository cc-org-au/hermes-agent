---
name: autoresearch
description: Run the CPU-friendly autoresearch workflow from efecanbasoz/autoresearch-cpu. Use when asked to set up, prepare, train, or iterate on the autoresearch repo on machines without GPUs, especially via the /autoresearch skill slash command.
---

# Autoresearch CPU

Use this skill for the CPU fork at `https://github.com/efecanbasoz/autoresearch-cpu`.

## Autonomous Run Contract

When this skill is launched from Hermes `/autoresearch`:

- Treat the newest `Hermes Runtime Instructions` block in `program.md` as the active run brief.
- Treat the user's immediately preceding `/autoresearch` reply as the only required interactive input for the run.
- Do not ask follow-up questions about run tags, branch tags, branch names, naming conventions, or similar setup details.
- If a branch name, run tag, or artifact label is needed, choose a deterministic default yourself and continue.
- If `program.md` or the newest Hermes Runtime Instructions block specifies a total outer runtime or wall-clock budget for the whole autoresearch loop, treat it as a hard stop for the overall run.
- If no total outer runtime is specified, default to 30 minutes total for the overall autoresearch loop rather than running indefinitely.
- Keep the outer-loop runtime budget separate from any per-run `train.py` budget that the repo itself enforces.
- Hermes `/autoresearch` background runs bypass the normal Hermes max-iterations cap for this run; outer runtime is the stop condition instead.
- Start work immediately.
- When safe and useful, split the work into a small number of parallel delegated subprocesses for distinct workstreams.
- Continue autonomously until the run is complete or a true human-only blocker is reached.
- Prefer concise milestone updates and a final summary over extra conversational back-and-forth.

## Repo Path

Default working clone:

```bash
$HERMES_HOME/skills/external-repos/autoresearch
```

If missing, clone it:

```bash
mkdir -p "$HERMES_HOME/skills/external-repos"
git clone https://github.com/efecanbasoz/autoresearch-cpu "$HERMES_HOME/skills/external-repos/autoresearch"
```

If it already exists, update it:

```bash
git -C "$HERMES_HOME/skills/external-repos/autoresearch" pull --ff-only
```

## Workflow

From the repo root:

```bash
uv sync
uv run prepare.py --num-shards 4
uv run train.py
```

Expected behavior:

- `prepare.py` downloads data and builds the tokenizer cache under `~/.cache/autoresearch/`.
- `train.py` runs a CPU-oriented training experiment with the fork's defaults.
- A full run can take tens of minutes on CPU hardware, so prefer background execution and monitor progress.

## What To Edit

- Edit `train.py` for experiment changes.
- Use `program.md` as the runbook for the autonomous iteration loop.
- Leave `prepare.py` alone unless the user explicitly asks to change data prep.

## Quick Checks

```bash
uv run python -c "import torch; print(torch.__version__)"
uv run python -c "import torch; print(torch.cuda.is_available())"
```

This fork is intended to work without CUDA, so `False` is fine.

## Guardrails

- Use a dedicated branch for experiment work if you are changing model code repeatedly.
- Do not assume a GPU exists.
- If a prior clone points at a different autoresearch remote, either update the remote or move it aside before cloning this CPU fork.
