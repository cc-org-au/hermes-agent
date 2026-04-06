# Archived scripts

These files were moved here from `scripts/` to keep the top-level scripts directory focused on **deploy, droplet, policy materialization, and install** paths that are referenced from docs and automation.

Nothing was deleted. Run them from the archive path (see each file’s header).

| File | Role |
|------|------|
| `hermes-gateway` | Legacy standalone gateway entry point (parallel to `hermes gateway` CLI). |
| `discord-voice-doctor.py` | Manual diagnostic for Discord voice setup. |
| `kill_modal.sh` | Stops Modal sandboxes tagged `hermes-agent` (or all with `--all`). |
| `sample_and_compress.py` | HuggingFace trajectory sampling / compression helper for RL-style workflows. |

If you promote a script back to active use, move it to `scripts/` and update any doc links.
