<!-- policy-read-order-nav:top -->
> **Governance read order** — step 56 of 58 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../../README.md)).
> **Before this file:** read [core/governance/generated/by_role/examples/README.md](../by_role/examples/README.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# Slack Department/Project/Task Routing Playbook

Purpose: enforce a predictable collaboration shape in Slack:
- channels represent departments
- threads represent projects/workstreams
- thread replies represent tasks/subtasks and execution updates

Status: non-canonical generated playbook for operational use.

## Routing Rules

1. Department channel creation
- Create a new channel only when no existing department channel matches the department slug.
- Naming: `dept-<department_slug>` (lowercase, hyphenated).
- Default visibility: public unless policy explicitly requires private.
- Immediately invite notification recipients after channel creation (for example platform operators and on-call users) so alerts are visible without manual join.

2. Project thread creation
- In the department channel, create one root message per project.
- Root message title format: `[PROJECT] <project_name>`.
- Thread replies under this root are the project timeline.

3. Task comment handling
- Every task update is posted as a reply in the owning project thread.
- Task entry format:
  - `[TASK:<id>] <title>`
  - `owner: <role_or_agent>`
  - `state: proposed|in_progress|blocked|done`
  - `next: <next_action>`

4. Escalation
- Blockers and incidents must be posted as task replies tagged with `state: blocked`.
- If severity is high/critical, mirror a short alert in the department channel with link to the task reply.

## Automation Conditions

- Auto-create department channel when:
  - a requested department slug does not resolve to an existing channel.
- Auto-invite required users when:
  - a new department channel is created, or
  - an existing department channel is selected but a required user is missing.
- Auto-create project thread when:
  - a project has no root thread in its department channel.
- Auto-reply task update when:
  - project thread exists and task metadata is present.

## Permissions Guidance (for multi-agent phase)

- Only designated orchestration agents may create channels.
- Project lead agents may create project threads in allowed department channels.
- Worker agents may only post task replies in assigned threads.

## Minimal Verification Checklist

- Channel created with expected `dept-` naming.
- Project root message posted in that channel.
- Thread reply posted with task metadata.
- Follow-up task update appended in same thread.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/scripts/README.md](../../../scripts/README.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
