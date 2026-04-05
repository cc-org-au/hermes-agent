<!-- policy-read-order-nav:top -->
> **Governance read order** — step 43 of 58 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/governance/standards/channel-architecture-policy.md](../standards/channel-architecture-policy.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

SUB-PROMPT — FUTURE CHANNEL ARCHITECTURE PLANNER

Design a future communications architecture for deployment across WhatsApp, Telegram, and Slack.

For now, this is planning only. Do not assume integrations are live.

Define:

GLOBAL CHANNELS
- operator-direct-line
- executive-briefings
- board-of-directors
- org-registry
- risk-and-incidents

DEPARTMENT CHANNELS
- engineering
- product
- operations
- it-security
- design
- commercial
- finance

PER-PROJECT CHANNELS
- project-[name]-lead
- project-[name]-delivery
- project-[name]-qa
- project-[name]-ops
- project-[name]-archive

For each channel, specify:
- purpose
- allowed participants
- posting rules
- summary cadence
- escalation path
- archival behavior

RULES

1. Keep channels purpose-specific.
2. Avoid redundant chatter.
3. Ensure summaries flow upward rather than raw execution noise.
4. Ensure operator-facing channels remain concise and strategic.
5. Preserve auditability and clean reporting lines.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/governance/standards/client-deployment-policy.md](../standards/client-deployment-policy.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
