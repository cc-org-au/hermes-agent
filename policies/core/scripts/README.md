<!-- policy-read-order-nav:top -->
> **Governance read order** — step 60 of 61 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../README.md)).
> **Before this file:** read [core/governance/generated/playbooks/slack-department-project-task-routing.md](../governance/generated/playbooks/slack-department-project-task-routing.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# Policies scripts — unified pipeline

All scripts are orchestrated by **`start_pipeline.py`** (single entry point). Run individual steps only for debugging.

## Entry point (use this)

| Command | Purpose |
|---------|---------|
| `python policies/core/scripts/start_pipeline.py` | Verify layout + **strict activation cues** on `policies/core/governance/standards/*.md`, regenerate `INDEX.md`, update `.pipeline_state/manifest.json`. |
| `python policies/core/scripts/start_pipeline.py --dry-run` | Verification only; prints manifest diff; **writes no files** (safe CI gate). |
| `python policies/core/scripts/start_pipeline.py --workspace-root "$AGENT_HOME/workspace" --policy-root "$AGENT_HOME/policies"` | Full runtime materialization: canonical policy bundle outside workspace + runtime-editable policy/agent files and `operations/` inside workspace. |
| `python policies/core/scripts/start_pipeline.py --init-operations` | Legacy mode: same as full run, then create missing `operations/*.md` stubs only. |
| `python policies/core/scripts/start_pipeline.py --no-strict` | Skip activation-cue checks (**not** for production). |
| `./policies/start_pipeline.sh` | Shell wrapper (same arguments as above). |

## Individual steps (subordinate)

| Script | Role |
|--------|------|
| `verify_policy_tree.py` | Structural checks + strict “Activation prompt” headings in `policies/core/governance/standards/*.md`. |
| `generate_index.py` | Regenerate `policies/INDEX.md`. |
| `apply_read_order_navigation.py` | Insert/update top/bottom read-order blocks on every `policies/**/*.md` (sequence: `READ_ORDER_SEQUENCE` in that file). **Run after** `generate_index.py` — `start_pipeline.py` runs both. |
| `pipeline_manifest.py` | Imported by `start_pipeline.py` — file hashes under `policies/`. |
| `init_operations_stubs.py` | Create missing operational register files under `operations/` (workspace root from `AGENT_WORKSPACE_ROOT` when set). |
| `materialize_role_workspace.py` | Create `policies/core/governance/generated/by_role/<slug>/` from template. |

## Typical flows

**Before deploy / after pulling git changes**

```bash
python policies/core/scripts/start_pipeline.py --dry-run && \
python policies/core/scripts/start_pipeline.py --workspace-root "$AGENT_HOME/workspace" --policy-root "$AGENT_HOME/policies"
```

**New clone**

```bash
python policies/core/scripts/start_pipeline.py --workspace-root "$AGENT_HOME/workspace" --policy-root "$AGENT_HOME/policies"
```

## Tests

```bash
pytest tests/policies/test_policy_pipeline.py -v
```

## Reliability notes

- **Strict mode** rejects `policies/core/governance/standards/*.md` files that omit the activation heading — policies cannot pass verification as empty placeholders.
- **Manifest** lives in `policies/.pipeline_state/` (gitignored); each successful run refreshes it so the next run can report what changed.
- **`--dry-run`** never writes INDEX or manifest, so it cannot falsely report “complete” after a broken tree.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [INDEX.md](../../INDEX.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
