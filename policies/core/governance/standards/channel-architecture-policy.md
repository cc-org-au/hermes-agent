<!-- policy-read-order-nav:top -->
> **Governance read order** — step 42 of 58 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/governance/role-prompts/task-state-evidence-enforcer.md](../role-prompts/task-state-evidence-enforcer.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# CHANNEL_ARCHITECTURE_POLICY.md

## Activation prompt (role reminder)

When enforcing this policy, load the associated prompt(s) **in the same session** so operational role constraints and tone stay aligned with governance:

- `../role-prompts/future-channel-architecture-planner.md`

---

## Purpose

This policy defines the future communications architecture for deployment across WhatsApp, Telegram, and Slack.

This is planning and documentation only until those integrations are explicitly activated.

---

## Global Channels

- `operator-direct-line`
- `executive-briefings`
- `board-of-directors`
- `org-registry`
- `risk-and-incidents`

## Department Channels

- `engineering`
- `product`
- `operations`
- `it-security`
- `design`
- `commercial`
- `finance`

## Per-Project Channels

- `project-[name]-lead`
- `project-[name]-delivery`
- `project-[name]-qa`
- `project-[name]-ops`
- `project-[name]-archive`

---

## Hard Rules

Every channel must define:
- purpose
- allowed participants
- posting rules
- summary cadence
- escalation path
- archival behavior

---

## Channel Principles

- channels must be purpose-specific
- avoid redundant chatter
- summaries must flow upward rather than raw execution noise
- operator-facing channels must remain concise and strategic
- project archive channels should contain non-active material
- risk channels should contain material incidents and blockers only

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/role-prompts/future-channel-architecture-planner.md](../role-prompts/future-channel-architecture-planner.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
