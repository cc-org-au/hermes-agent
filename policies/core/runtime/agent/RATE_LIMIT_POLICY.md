<!-- policy-read-order-nav:top -->
> **Governance read order** — step 23 of 58 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/runtime/agent/SECURITY.md](SECURITY.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# RATE_LIMIT_POLICY.md — Token budgets and compaction

This file is part of the attached workspace agent markdown pack.

Use it after `AGENTS.md` when long-running context, compaction, or orchestration limits matter.

## Purpose
Keep orchestrator and lead sessions within practical model context limits while preserving continuity.

Before aggressive compaction, write or update archival entries under `operations/projects/<slug>/memory/archival/` per `policies/core/governance/artifacts-and-archival-memory.md` so recall is not lost.

This file governs context economy, not security authority.
It must operate inside the canonical deployment and security framework.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/runtime/agent/TOOLS.md](TOOLS.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
