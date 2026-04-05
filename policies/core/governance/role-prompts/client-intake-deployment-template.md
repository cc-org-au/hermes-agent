<!-- policy-read-order-nav:top -->
> **Governance read order** — step 45 of 58 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/governance/standards/client-deployment-policy.md](../standards/client-deployment-policy.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# SUB-PROMPT — CLIENT INTAKE & DEPLOYMENT TEMPLATE

## Purpose

Activate when operating under `policies/core/governance/standards/client-deployment-policy.md` (and related deployment work). This prompt reminds the agent of **intake questions, scoping, and deployment boundaries** for client-facing or internal “client” workstreams.

## Instructions

1. Confirm authority and Human Operator approval for the engagement.  
2. Capture requirements, constraints, data boundaries, and success metrics in writing.  
3. Map the engagement to **project slug** and `operations/projects/<slug>/` per `policies/core/governance/artifacts-and-archival-memory.md`.  
4. Do not store secrets in prompts or generated markdown.  
5. Escalate ambiguities to Project Lead or orchestrator before irreversible deployment steps.

## Output

Produce or update a client intake summary suitable for `operations/projects/<slug>/artifacts/` or governed `policies/core/governance/generated/`.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/standards/agent-lifecycle-org-hygiene-policy.md](../standards/agent-lifecycle-org-hygiene-policy.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
