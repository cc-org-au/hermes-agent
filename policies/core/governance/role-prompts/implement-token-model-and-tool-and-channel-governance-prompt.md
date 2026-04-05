<!-- policy-read-order-nav:top -->
> **Governance read order** — step 14 of 58 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/governance/standards/token-model-tool-and-channel-governance-policy.md](../standards/token-model-tool-and-channel-governance-policy.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# Implement — token, model, tool, and channel governance

## Purpose

This is the implementation prompt for the additive token/model/tool/channel governance layer.

It should be given to the root deployment agent or to the builder/runtime layer after the canonical deployment and security architecture already exists.

It adds:
- token governance
- model routing
- consultant controls
- tool/skill delegation
- provider rate-limit protection
- messaging-channel governance

It does not replace the earlier constitutional layer.

---

## Implementation Prompt

```text
Implement the additive governance defined in policies/core/governance/standards/token-model-tool-and-channel-governance-policy.md (canonical read-order: read that standard immediately before this prompt).

Your role is to integrate this policy into the existing AI-company architecture without restating or weakening earlier policies.

You must treat the following as already authoritative:
- the canonical deployment pack
- the unified deployment and security runbook
- the existing hierarchy, memory, escalation, and least-privilege rules
- the existing security governance system

Your job is to add a model-routing and token-governance layer that makes the system:
1. use the least tokens and least memory possible without materially degrading quality
2. avoid provider abuse, spam, or rate-limit pressure
3. use cheap/free/open models by default where quality permits
4. reserve premium models for bounded consultant calls
5. constrain tool and skill assignment by role and necessity
6. clearly govern communication channels to the human operator
7. support self-improvement without runaway spend

Implementation tasks:

1. Create or update the model-governance records needed to operationalize this policy.
2. Add a model-routing registry that records:
   - role
   - default model
   - fallback model
   - premium escalation model(s)
   - default reasoning level
   - maximum allowed reasoning level
   - consultant eligibility
3. Add a consultant-request template that requires:
   - requester
   - task digest
   - current model
   - failure evidence
   - at least two candidate consultant models
   - why a cheaper option is insufficient
   - expected token/cost budget
   - modality needs
4. Add a consultant-challenge template requiring another agent to argue against or refine the consultant request before approval.
5. Add rolling budget guards for:
   - premium consultant request share
   - premium token share
   - premium spend share
   - per-task-tree consultant count
6. Add rate-limit protection logic with:
   - exponential backoff with jitter
   - per-role request caps
   - per-model concurrency caps
   - per-provider concurrency caps
   - retry ceilings
   - queueing for non-urgent work
7. Add a delegation packet template requiring:
   - task id
   - assigned model
   - reasoning level
   - allowed tools/skills
   - scope boundary
   - success test
   - escalation threshold
   - context capsule
   - max token budget
8. Add tool and skill governance records that map tool classes to role authority.
9. Add automatic privilege revocation rules for:
   - task completion
   - role changes
   - notable misuse
   - unnecessary retention
   - security-triggered downgrade
10. Add channel-governance rules for:
   - WhatsApp DM to operator
   - Telegram DM to operator
   - Telegram group/topic
   - Slack DM
   - Slack channels and threads
11. Ensure all human-visible channel messages end with a role-only disclosure line:
   - `--<Exact Role Name>`
12. Ensure the Chief Orchestrator is the only role that can approve premium consultant calls after challenge and consensus.
13. Ensure workers cannot self-call premium consultant models.
14. Ensure supervisors can request escalation but cannot approve premium consultant use.
15. Ensure Directors, Project Leads, and Org/HR can participate in consultant deliberation but not bypass the Chief.
16. Ensure free models and free routers are restricted to non-critical, non-sensitive, non-deterministic work.
17. Ensure messaging escalation to the human operator follows the defined hierarchy:
   - WhatsApp highest priority, output/status only
   - Telegram DM for direct strategic discussion
   - Telegram group/topic for high-level topic discussion
   - Slack DM as board layer
   - Slack channels/threads as operating substrate
18. Ensure the system archives rather than destroys channels, threads, and projects unless the operator explicitly approves destruction.
19. Ensure self-improvement loops have explicit cost windows, stop conditions, and no recursive premium-consult abuse.
20. If a current default model named in the policy is unavailable in the environment, choose the nearest available model in the same tier and record the substitution with justification.

Operational rules:
- do not widen privileges for convenience
- do not make premium models the default for prestige reasons
- do not let the chief retain bloated memory
- do not let Slack become a raw-log dump
- do not let Telegram or WhatsApp become general chatter channels
- do not let free-model randomness govern important decisions
- do not let consultant requests proceed without a challenger
- do not let repeated warning signs remain unbudgeted or unlogged

Required deliverables:
1. model routing registry
2. consultant request template
3. consultant challenge template
4. role-to-model assignment matrix
5. tool/skill authority matrix
6. rolling token/spend guard definitions
7. channel governance matrix
8. escalation rules for premium consultant use
9. any required updates to operational records or bootstrapping files
10. a concise summary of what was added

Decision standard:
If there is ambiguity, choose the interpretation that reduces token burn, reduces privilege, reduces human interruption, and preserves final quality.
```

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/runtime/agent/BOOTSTRAP.md](../../runtime/agent/BOOTSTRAP.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
