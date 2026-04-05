# Security alert register (Session 11 — remediation queue)

> **Profile:** `chief-orchestrator` · **HERMES_HOME:** `…/profiles/chief-orchestrator`  
> **Purpose:** Track open security warnings; record resolution and evidence. Review after infra or policy changes.

## Active warnings

| ID | Summary | Severity | Status | Owner | Evidence / resolution |
|----|---------|----------|--------|-------|----------------------|
| W001 | Unknown service on port **40227** | Medium | **MITIGATED** | Operator | **Identified:** SSH management listener on alternate port. **Control:** Tailscale-only exposure per **REM-001** / `scripts/harden_ssh_management_port_tailscale.sh` + `policies/core/security-first-setup.md`. **Verify on VPS:** `ss -tlnp | grep 40227` (expect `sshd`), `iptables-save` / `nft` rules as documented. |
| W002 | Browser automation strategy undocumented | Low | **DOCUMENTED** | Chief / AG-008 | **Strategy:** Primary **Browserbase** (or configured remote browser) for automation. Local **Camofox** only with isolated profile, `browser.allow_private_urls: false` in production unless approved. See `CHANNEL_ARCHITECTURE.md` § Browser + `security-foundation-agents-role-prompts.md` § AG-008. |
| W003 | Integration allowlists documented | Medium | **COMPLETE** | AG-009 / Operator | **`CHANNEL_ARCHITECTURE.md`** generated from live `.env` via `scripts/render_workspace_registers_from_env.py`. Add `*_ALLOWED_CHATS` / `*_ALLOWED_CHANNELS` when locking public surfaces; restart gateway after `.env` edits. |
| W004 | Skill inventory register | Low | **COMPLETE** | AG-012 | **`SKILL_INVENTORY_REGISTER.md`** generated from `HERMES_HOME/skills/`; refine permissions column from each `SKILL.md`. |

## Closed / historical

(Add rows when warnings are fully retired; keep one-line pointer to date and commit or log file.)

## Links

- `CHANNEL_ARCHITECTURE.md`
- `policies/core/governance/standards/canonical-ai-agent-security-policy.md`
- Gateway allowlist implementation: `gateway/run.py` (integration surface checks)
