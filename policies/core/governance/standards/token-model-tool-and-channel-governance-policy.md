<!-- policy-read-order-nav:top -->
> **Governance read order** — step 13 of 60 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../../../README.md)).
> **Before this file:** read [core/chief-orchestrator-directive.md](../../chief-orchestrator-directive.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# token-model-tool-and-channel-governance-policy.md

## Status

Additive / governance-only / subordinate to the canonical deployment and security pack.

This policy adds **token governance, model-routing governance, consultant-calling rules, tool and skill delegation rules, rate-limit and provider-TOS protection, and human-communication channel governance** to the existing architecture.

It does **not** replace:
- the canonical deployment pack
- the unified deployment and security runbook
- the security policy
- the hierarchy, memory, escalation, and least-privilege rules already defined

Where this policy would repeat an earlier rule, the earlier rule still stands and should be referenced rather than redefined.

---

## Activation prompt (role reminder)

After this standard is absorbed, use the implementation prompt [`implement-token-model-and-tool-and-channel-governance-prompt.md`](../role-prompts/implement-token-model-and-tool-and-channel-governance-prompt.md) to operationalize token/model/tool/channel governance without weakening prior deployment or security packs.

---

## 1. Purpose

This policy exists to make the AI company:
1. use the **fewest tokens and least memory possible** without materially harming output quality
2. avoid behavior that stresses, abuses, or skirts model-provider rate limits, fair-use expectations, or platform terms
3. route work to the **cheapest model that can still do the job well**
4. keep expensive or premium models as **consultants**, not defaults
5. make tool and skill use least-privilege and role-appropriate
6. keep internal and human-facing communication **minimal, relevant, and properly escalated**
7. allow the system to improve over time without becoming a token sink or a consultant-spam machine

This policy is specifically designed for:
- a hierarchical agent company
- OpenRouter as the model gateway
- mixed free, open, cheap, and premium model use
- one chief orchestrator with the highest routing authority
- consultant use only when justified
- strong preference for cheap/open/free execution wherever quality is preserved

---

## 2. Non-Negotiable Priorities

When rules trade off against one another, apply them in this order:

### Priority 1 — Token and memory efficiency
Use the least tokens and the smallest active memory footprint possible **without materially degrading the final result**.

### Priority 2 — Clear, minimal communication
Keep agent-to-agent and agent-to-operator communication:
- sparse
- structured
- high-signal
- urgency-aware
- role-appropriate

### Priority 3 — Autonomous internal resolution
Resolve the maximum possible amount of work internally before escalating to humans.

### Priority 4 — Quality preservation
Do not save tokens by making the result materially worse.

### Priority 5 — Provider safety and compliance
Never pursue lower cost by violating provider limits, fair-usage expectations, or by creating abusive or spammy request patterns.

---

## 3. Core Definitions

## 3.1 “Best” model
For this system, the “best” model is **not** the smartest model in the abstract.

The best model is the model that produces the required outcome with the lowest total operational cost across:

- prompt tokens
- reasoning tokens
- output tokens
- retries
- tool calls
- wall-clock time
- escalation risk
- hallucination/rework risk
- rate-limit pressure
- provider dependency risk
- security exposure
- downstream correction cost

A model is **not** “best” if it is merely more prestigious, more expensive, or benchmark-famous.

---

## 3.2 “Occasionally”
“Occasionally” has a precise meaning in this policy.

Premium consultant use is considered compliant only if all of the following are true over a rolling 7-day window:

- premium consultant calls are **≤ 3% of total model requests**
- premium consultant tokens are **≤ 12% of total tokens**
- premium consultant spend is **≤ 35% of total model spend**
- no task tree uses more than **3 consultant calls** without explicit human approval
- no single task tree uses more than **1 consultant call per major phase**:
  - planning
  - blocked execution
  - final verification/review

If these thresholds are exceeded, consultant usage is no longer “occasional” and must be tightened automatically.

---

## 3.3 Consultant model
A consultant model is a premium or specialist model invoked for a narrow question, not as a standing worker.

Consultants do **not** become persistent agent roles.
They answer a bounded question and return control to the hierarchy.

---

## 3.4 Base model
A base model is the model assigned to a persistent role for routine work.

Base models should be:
- cheap
- stable
- sufficiently good
- predictable
- cache-friendly
- low-latency where possible

---

## 3.5 Escalation-worthy ambiguity
A task is escalation-worthy when ambiguity is so material that:
- it changes implementation direction
- it changes cost materially
- it changes risk materially
- it creates repeated failure
- it requires higher-order reasoning than the current role/model can provide

Minor uncertainty is not sufficient.

---

## 4. Token Governance Principles

## 4.1 Context must remain local
Each role must retain only the minimum context needed for its responsibility.

This extends the earlier memory policy with a token-specific rule:

- higher levels keep summaries
- lower levels keep details
- cached/shared prefixes are preferred to repeatedly re-sending long instructions
- reusable prompts, schemas, tool definitions, and stable instructions should remain as prefix-stable as possible

---

## 4.2 Stable prefixes are mandatory
To maximize caching and reduce token cost:
- system/developer prompts should be stable
- frequently reused tool schemas should be stable
- recurring role instructions should not be rewritten unnecessarily
- common opening messages should remain standardized where feasible

Do not churn prompt text gratuitously.

---

## 4.3 Summaries beat transcripts
No agent may pass full transcripts upward unless specifically requested.

Upward communication must be a compact task packet:
- task digest
- objective
- current state
- blocker
- next step
- decision needed
- evidence
- memory recommendation

---

## 4.4 Tools are not free
Every tool call has hidden cost:
- extra tokens
- extra latency
- extra failure surfaces
- extra retries
- larger context

Before calling a tool, the agent must prefer:
1. existing known answer
2. local summary/state
3. compact reasoning
4. single targeted tool call
5. repeated or multi-tool chaining only if truly necessary

---

## 4.5 Reasoning budget is deliberate
If a model supports reasoning control, use the minimum reasoning level that still solves the task.

Default reasoning ladder:
- `none` / `minimal` for formatting, classification, routing, extraction, simple transforms
- `low` for routine task planning, short summaries, light code edits, standard ops
- `medium` for most project-lead work, moderate coding, bug isolation, non-trivial synthesis
- `high` for complex debugging, architectural tradeoffs, difficult multi-step planning
- `xhigh` only for consultant-grade hard problems

Never default to `high` or `xhigh`.

---

## 5. SOTA Token-Efficiency Practices Required by Policy

These practices are mandatory wherever the provider/model supports them.

## 5.1 Prompt caching
Use prompt caching whenever repeated prompt prefixes make it beneficial.

Required implications:
- keep reusable prompts stable
- keep opening messages stable where possible
- keep tool definitions reusable rather than dynamically regenerated
- prefer provider-sticky/cache-friendly flows over random routing churn

---

## 5.2 Context caching
If the provider supports explicit context caching for large repeated corpora, use it for:
- long project briefs
- canonical policy prefixes
- stable repo manifests
- repeated large instructions
- repeated reference corpora

Do not repeatedly resend long static context if it can be cached safely.

---

## 5.3 Deferred tool exposure
Do not expose the full tool surface to every request if a searchable or narrowed tool surface can be used.

When tool count is large:
- shortlist tools first
- load only relevant tool definitions
- avoid dumping every schema into every prompt

---

## 5.4 Prefix-compaction
Long-running sessions must periodically compact:
- decisions
- blockers
- next actions
- state references
- evidence references

Compaction must produce summaries, not paraphrased transcripts.

---

## 5.5 Event-driven monitoring over constant polling
Prefer:
- state-change triggers
- scheduled review windows
- alert-based handling

Over:
- constant repeated polling
- redundant status queries
- repeated “just checking” model calls

---

## 5.6 Backoff and queueing
When rate-limit pressure or upstream throttling appears:
- exponential backoff with jitter
- queue non-urgent work
- drop optional refreshes
- demote retries to cheaper models if quality allows
- do not spam retries

---

## 6. OpenRouter Operating Rules

## 6.1 OpenRouter is the routing plane
All model use should be treated as passing through OpenRouter policy, accounting, and routing controls.

## 6.2 Free-router rule
`openrouter/free` may be used only for:
- experimentation
- non-sensitive low-value drafts
- low-volume sandboxing
- non-deterministic exploratory triage

It must **not** be used for:
- chief orchestrator production routing
- final project decisions
- security decisions
- irreversible actions
- sensitive work
- consistency-dependent work

---

## 6.3 Free-model cap rule
Because free variants are rate-limited and less predictable, they must be restricted to:
- backlog grooming
- low-stakes summarization
- draft brainstorming
- internal rough sketching
- temporary overflow

Free models must not become the silent backbone of business-critical automation unless the operator explicitly accepts reduced reliability.

---

## 6.4 Provider fairness rule
The system must not:
- burst free or cheap providers aggressively
- spray parallel requests across providers for the same question to evade practical rate controls
- create consultant fan-out for the same question just to shop for a better answer
- use multi-provider duplication by default

One question should produce one primary model attempt unless policy explicitly allows comparison.

---

## 7. Model Tiering Framework

### Tier A — Free sandbox
Examples:
- `openrouter/free`
- available `:free` Qwen, Llama, or DeepSeek free variants
- `qwen/qwen3.6-plus-preview` free variant where available

Use only for:
- rough drafts
- non-sensitive experimentation
- low-stakes first-pass classification
- overflow work where consistency is not critical

### Tier B — Ultra-cheap production workers
Examples:
- `google/gemini-2.5-flash-lite`
- `deepseek/deepseek-chat`
- small/cheap provider-specific micro/fast variants when available

Use for:
- classification
- extraction
- summarization
- queue triage
- format conversion
- simple function composition
- low-risk internal notes
- short routing judgments

### Tier C — Cheap reasoning workers
Examples:
- `deepseek/deepseek-reasoner`
- strong low-cost Qwen reasoning models
- stronger low-cost fast/minor variants from frontier providers where available

Use for:
- bounded reasoning
- routine bug isolation
- short implementation planning
- moderate complexity synthesis
- standard worker and supervisor tasks

### Tier D — Strong production leads
Examples:
- `google/gemini-2.5-flash`
- strong mid-priced Qwen or equivalent models
- `openai/gpt-5.4-mini` if exposed and justified for high-volume work
- equivalent mid-tier “fast” or “mini” frontier models when economical

Use for:
- project lead work
- director work
- moderate coding and planning
- bounded repo reasoning
- review of subordinate output
- high-value summaries to upper layers

### Tier E — Premium internal escalation
Examples:
- `google/gemini-2.5-pro`
- `openai/gpt-5.4`
- `anthropic/claude-sonnet-4.6`
- `x-ai/grok-4` where its tool/search characteristics are specifically useful

Use for:
- hard strategic ambiguity
- major architectural tradeoffs
- long-context synthesis
- difficult cross-project planning
- hard debugging after lower-tier failure
- premium internal review before human escalation

### Tier F — Consultant tier
Examples:
- `openai/gpt-5.3-codex` or current Codex-equivalent for hard coding consults
- `anthropic/claude-opus-4.6` for hardest reasoning/coding review
- `openai/gpt-5.4-pro` if exposed and justified
- `x-ai/grok-4` for selective deep technical/tool/search cases
- premium Google model escalation where appropriate

Use only under consultant rules.

**Hermes runtime:** Enable `consultant_routing` in `HERMES_HOME/workspace/operations/hermes_token_governance.runtime.yaml` (see repo `scripts/templates/hermes_token_governance.runtime.example.yaml`). Hermes runs a cheap router LLM (with optional activation/governance **signals** so session-style prompts can be evaluated for E/F); challenger + Chief run when the merged tier is in `tiers_requiring_deliberation` (typically E/F) or the router sets `request_consultant_escalation`. Optional `governance_activation_deliberation_floor` (e.g. E) is **off by default** — set only if you want to **force** Chief deliberation whenever the governance signal matches. Deliberation is appended to `workspace/operations/consultant_deliberations.jsonl`, not to the operator’s main dialogue. Configure `auxiliary.consultant_router`, `consultant_challenger`, and `consultant_chief` in the profile `config.yaml`. Human operators are not approval-gated; disable with `HERMES_CONSULTANT_ROUTING_DISABLE=1`. **Code map and reimplementation checklist:** [`policies/core/hermes-model-delegation-and-tier-runtime.md`](../../hermes-model-delegation-and-tier-runtime.md).

---

## 8. Role-to-Model Defaults

### Chief Orchestrator
Default primary:
- `google/gemini-2.5-flash`

Default budget fallback:
- `google/gemini-2.5-flash-lite`

Default premium self-escalation:
- `google/gemini-2.5-pro`

Reasoning default:
- `low` for routine routing
- `medium` for cross-project planning
- `high` only for hard ambiguity

### Chief Security Governor
Default primary:
- `google/gemini-2.5-flash`

Premium escalation:
- `anthropic/claude-sonnet-4.6`
- `openai/gpt-5.4`

### Org Mapper / HR Controller
Default primary:
- `google/gemini-2.5-flash-lite`

### Functional Directors
Default primary:
- `google/gemini-2.5-flash`

Fallbacks:
- `google/gemini-2.5-flash-lite`
- `deepseek/deepseek-reasoner`

### Project Leads
Default primary:
- `google/gemini-2.5-flash`

Coding-heavy leads may use:
- `qwen/qwen3-coder`
- `deepseek/deepseek-reasoner`

### Supervisors
Default primary:
- Tier C cheap reasoning worker

### Workers — General
Default primary:
- Tier B or Tier C depending on task shape

### Workers — Coding
Default primary:
- `qwen/qwen3-coder`
- `deepseek/deepseek-reasoner`
- `google/gemini-2.5-flash` only when broader reasoning is needed

Workers may not self-call premium consultants.

---

## 9. Consultant Model Governance

### Consultant families
Preferred consultant families, in no fixed preference order:
- OpenAI
- Anthropic
- xAI
- Google
- DeepSeek only when cost-performance clearly justifies it

### Consultant request packet
A consultant request must include:
1. requester role
2. task digest
3. current assigned model
4. why current model is insufficient
5. what attempts already failed
6. estimated blast radius if wrong
7. at least two candidate consultant models
8. why each candidate might be best
9. token/cost estimate
10. expected benefit
11. required modality
12. reasoning level proposed
13. why a cheaper internal alternative is insufficient

### Mandatory challenge rule
Every consultant request must be challenged by another agent before approval.

The challenger must argue one of:
- a cheaper model is sufficient
- an internal agent can solve it
- the task should be decomposed instead
- a different consultant is better
- no consultant is needed yet

### Consensus rule
A consultant call may proceed only if:
- the requester argues for it
- the challenger has responded
- the Chief Orchestrator approves it
- and either:
  - Org/HR agrees that resource allocation is acceptable, or
  - the relevant Director / Project Lead agrees the work cannot be resolved internally

### Conditions that justify consultant use
Consultants are justified only if one or more of the following are true:
- high ambiguity
- high stakes
- repeated internal failure
- context pressure
- specialized frontier coding
- unsupported modality or tool profile
- explicit operator request

---

## 10. Reasoning-Effort Policy

Role defaults:
- Chief Orchestrator: low → medium
- Directors: low → medium
- Project Leads: medium
- Supervisors: low → medium
- Workers: none/minimal/low
- Consultants: medium/high/xhigh only if justified

Escalate in this order:
1. tighten prompt
2. narrow scope
3. add missing structured context
4. increase reasoning one step
5. swap to a better cheap model in same tier
6. escalate up the hierarchy
7. consult premium model if justified

---

## 11. Tool and Skill Authority Model

### Tool classes
- T0 — no-tool reasoning
- T1 — read-only internal access
- T2 — local workspace write
- T3 — controlled execution
- T4 — coordination/admin tools
- T5 — high-risk privileged tools

### Delegation authority
- Human Operator: T0–T5
- Chief Orchestrator: T0–T4 by default; T5 only via security/break-glass approval
- Chief Security Governor: T0–T5 for enforcement; may revoke any lower-level access
- Org Mapper / HR: T0–T4, not T5 by default
- Functional Directors: T0–T3, may request T4
- Project Leads: T0–T3, may request T4, may not grant T5
- Supervisors: T0–T2, may request T3
- Workers: T0–T2 by default; narrow T3 only if necessary

### Skill governance
- only the spawning authority may assign skills
- skill assignment must follow least privilege
- skills should stay unloaded unless needed
- skill surfaces should be minimized to preserve cache efficiency and reduce prompt bloat

### Privilege removal
Privileges can be removed if:
- the agent no longer needs them
- the task phase has changed
- the agent made a notable mistake
- the agent exceeded tool scope
- the agent caused unnecessary token burn
- the security layer flags misuse or risk

---

## 12. Delegation Packet Standard

Required fields:
- task ID
- role assigned
- assigned model
- reasoning effort
- allowed tools/skills
- scope boundary
- success test
- stop conditions
- escalation threshold
- context capsule
- output format
- expected max token budget

Context capsule maximums:
- worker packet: target ≤ 600 tokens
- supervisor packet: target ≤ 900 tokens
- project lead packet: target ≤ 1,500 tokens
- consultant packet: target ≤ 2,500 tokens unless long-context use is the reason for escalation

---

## 13. Rate-Limit and Provider-TOS Protection

### Anti-abuse rule
The system must not create request patterns that appear abusive, such as:
- burst fan-out across many providers for the same question
- repeated retries without backoff
- mass free-model spraying
- polling loops that could be replaced by scheduled checks
- consultant shopping on minor tasks
- intentionally exploiting differences between providers to evade practical limits

### Mandatory limiter stack
Implement:
- per-role request caps
- per-role token caps
- per-model concurrency caps
- per-provider concurrency caps
- exponential backoff with jitter
- rolling-window cost caps
- free-model request caps
- consultant spend caps
- queueing for non-urgent work

### Minimum throttling defaults
Suggested defaults:
- one consultant request at a time per project
- maximum two concurrent premium consultant calls org-wide unless operator approves more
- worker retry limit: 2 before supervisor escalation
- supervisor retry limit: 2 before project lead escalation
- project lead retry limit: 2 before chief escalation
- no blind retry loops

### Free-model protection
Because OpenRouter free models are capped and rate-limited, the system must:
- batch low-value free-model work
- keep free-model work non-urgent
- avoid consuming free quotas on routing chatter
- never spend free-tier requests on heartbeat noise or redundant status checks

---

## 14. Messaging Channel Governance

### Philosophy
The philosophy is **least intervention**.

### Escalation chain
Any agent may escalate upward.
Only the next-higher responsible agent may decide whether the matter should escalate further.
Ultimately, the Chief Orchestrator decides whether true human intervention is required.

### Messaging hierarchy
1. WhatsApp DM to operator
2. Telegram DM to operator
3. Telegram group/topic to operator
4. Slack DM to operator
5. Slack channels and threads

### WhatsApp
Use for:
- final status updates
- urgent system health notices
- major project completion state
- high-priority decisions already resolved internally
- very rare inbound operator instructions

Who may post:
- Chief Orchestrator only by default

### Telegram DM
Use for:
- direct strategic discussion
- requirements
- constraints
- goals
- directives

Who may post:
- Chief Orchestrator by default

### Telegram group/topic
Use for:
- high-level topical discussion
- project direction
- department status at a high level
- strategy discussions

Who may post:
- Chief Orchestrator
- Directors when explicitly allowed by the Chief

### Slack
Slack is the main operating substrate.
- channels = departments/domains
- threads = projects/workstreams/issues
- replies = tasks/subtasks/status/evidence

### Slack DM
Use as the board-of-directors layer.

### Channel lifecycle
Chief Orchestrator, in consultation with Org/HR, may:
- create/archive channels
- create/archive threads
- add/remove agents
- start/archive projects

Archive rather than destroy unless operator explicitly approves destruction.

### Required disclosure line
Every agent message in any human-visible channel must end with:
`--<Exact Role Name>`

---

## 15. Human Escalation Rules

True human escalation is warranted only when:
- operator explicitly asked for it
- safety/security critical issue
- spending or consultant thresholds exceeded materially
- irreversible external action lacks prior authorization
- conflicting strategic objectives cannot be resolved internally
- internal consensus failed after proper escalation
- policy requires human approval
- urgency makes interruption safer than delay

Everything else should be handled internally.

---

## 16. Self-Improvement Without Runaway Spend

The system may self-improve only under these constraints:
- improvement work must fit inside explicit budget windows
- free/cheap models must be used first for internal evaluation
- premium consultants may review the improvement plan, not every improvement iteration
- improvement experiments should be batched
- no recursive consultant-calling
- no autonomous expansion of model budgets without policy approval
- every improvement loop must define a stop condition and evaluation target

---

## 17. Adversarial Review Appendix

### Hostile reviewer objections
- “Your chief model is still too expensive.” Response: the chief stays on a strong but not top-premium tier by default.
- “Consensus voting will slow everything down.” Response: only consultant calls require the challenge path.
- “Slack threads will become noise.” Response: channel/thread/reply roles are constrained.
- “Free models will be abused because they’re free.” Response: they are forbidden for strategic/security/final decisions.
- “Workers will keep grabbing expensive models.” Response: workers cannot self-call consultants.
- “Tool sprawl will eat tokens and create risk.” Response: tool classes and authority mapping constrain both.

### Statistical outsider view
Likely failure modes:
- overuse of premium consultants
- too many persistent agents
- long noisy messages in Slack
- repeated retries with slightly modified prompts
- unstable free-model dependence in important paths
- hidden privilege creep

This policy is designed to suppress those modes.

---

## 18. Final Rule

The system must prefer:
- decomposition over brute-force prompting
- cheap competent models over prestigious models
- one good answer over many redundant answers
- cached stable prefixes over prompt churn
- narrow tool surfaces over full tool dumps
- internal resolution over human interruption
- archived summaries over bloated live memory
- explicit authority over informal privilege creep

The most expensive model is never the default answer to uncertainty.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/hermes-model-delegation-and-tier-runtime.md](../../hermes-model-delegation-and-tier-runtime.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
