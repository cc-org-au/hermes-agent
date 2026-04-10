# Hermes Agent - Development Guide

Instructions for AI coding assistants and developers working on the hermes-agent codebase.

## Development Environment

```bash
source venv/bin/activate  # ALWAYS activate before running Python
```

**direnv (`.envrc`):** Prefer **`./venv/bin/python`** for `HERMES_REAL_BIN` (or `./venv/bin/hermes`). Do **not** run `command -v hermes` *before* `PATH_add scripts/core` — that captures a **global** install. The repo’s **`scripts/core/hermes`** shim runs **`venv/bin/python -m hermes_cli.main`** first (avoids a stale **`venv/bin/hermes`** shebang if the checkout moved). **`PATH_add scripts/shell`** exposes **`operator`**, **`droplet`**, and **`droplet_direct`**: bare **`operator`** opens an interactive SSH session on the **Mac mini** as **`MACMINI_SSH_USER`** (via **`scripts/core/ssh_operator.sh`**, venv-aware shell). Bare **`droplet`** opens an interactive SSH session as **`hermesuser`** (via **`scripts/core/ssh_droplet_user.sh`**); **`droplet git status`** runs one remote command as **`hermesuser`**. **Trailing `droplet` (Hermes VPS hop)** is different: handled inside **`hermes_cli.main`** when **`droplet` is the last argument** — **`hermes doctor droplet`**, **`hermes tui droplet`**, etc. exec **`agent-droplet`**. **Trailing `operator` (Mac mini hop)** is the same pattern: **`hermes doctor operator`**, **`hermes tui operator`**, etc. exec **`agent-operator`**. Pip/wheel installs include those files next to the package — you do **not** need **`scripts/core`** on `PATH` ahead of **`venv/bin`** for the hop to work. **`hermes tui`** is an alias for **`hermes chat`** (interactive CLI). **`hermes droplet --help`** / **`hermes operator --help`** document the subcommands; **`droplet`** is not a valid profile name (`hermes -p droplet` is wrong). The mini hop uses **`operator` as the final argv token** (e.g. **`hermes doctor operator`**). Do not use the profile name **`operator`** — it conflicts with the **`hermes operator`** CLI hop (same class as other top-level subcommands).

**Shell outside the repo (Mac/Linux):** With direnv in the checkout, **`operator`** / **`droplet`** / **`droplet_direct`** are already on **`PATH`**. Else set **`HERMES_AGENT_REPO`** and source **`scripts/shell/hermes-env.sh`** from **`~/.zshrc`** / **`~/.bashrc`** (default repo: **`$HOME/hermes-agent`** or **`$HOME/operator`**). That defines **`hermes()`**, **`operator()`**, **`droplet()`**, and **`droplet_direct()`**. Export **`HERMES_HOME`** before sourcing if your runtime lives under the checkout (e.g. **`export HERMES_HOME="$HOME/operator/.hermes"`**). **`~/.env/.env`**: droplet **`SSH_*`**; Mac mini **`MACMINI_SSH_*`** (and optional **`SSH_IP_OPERATOR`**); **`~/.env/.ssh_key`** or **`MACMINI_SSH_KEY`**. Remote shells activate the checkout **`venv`** via **`droplet_remote_venv.sh`** / **`operator_remote_venv.sh`**. On the VPS, **`agent-droplet`** runs **`./venv/bin/python -m hermes_cli.main`**. On the mini, **`agent-operator`** does the same over SSH.

### Mac mini SSH (`operator` hop)

- **Mini hop (suffix only):** put **`operator` as the last argument** — e.g. **`hermes doctor operator`**, **`hermes tui operator`**. Configure **`MACMINI_SSH_USER`**, **`MACMINI_SSH_HOST`**, **`MACMINI_SSH_PORT`** (e.g. 52822), and key path in **`~/.env/.env`** (see **`scripts/core/ssh_operator.sh`**). **`scripts/core/agent-operator`** runs **`./venv/bin/python -m hermes_cli.main`** on the mini with **`-p`** from your workstation **`~/.hermes/active_profile`** (default **`chief-orchestrator`**). Bare **`operator`** (on **`PATH`** via **`scripts/shell/operator`**) opens an interactive shell with repo **`venv`** activated on the mini.
- **Sudo on the mini (not the droplet):** **`ssh_operator.sh`** does **not** use **`sudo -S`**. Default **`HERMES_OPERATOR_REQUIRE_SUDO_SESSION=0`** — no **`sudo -v`** gate (the **`operator`** account often has **no** **`sudoers`** entry; a failed **`sudo -v`** would close SSH immediately). **Opt-in strict gate:** **`export HERMES_OPERATOR_REQUIRE_SUDO_SESSION=1`** (e.g. in **`~/.zshrc`**) after **`operator`** is in **`sudoers`** — then **`/dev/tty`** reattach, **`sudo -k`**, **`sudo -v`** must succeed before the remote shell or **`hermes …`**. Optional: **`HERMES_OPERATOR_SUDO_VERIFY_SOFT=1`** (**`sudo -v || true`** when REQUIRE=0). See **`/etc/sudoers`** / **`pam_tid`** if **`sudo`** never prompts when you run it by hand.

### Droplet SSH (automation vs interactive Hermes)

- **VPS hop (suffix only):** put **`droplet` as the last argument** — e.g. **`hermes droplet`**, **`hermes doctor droplet`**, **`hermes tui droplet`**. There is **no** `droplet` profile; do not set **`~/.hermes/active_profile`** to **`droplet`**. From the repo, **`PATH_add scripts/core`** makes **`scripts/core/hermes`** the preferred `hermes` binary (it delegates when the last token is **`droplet`**). **`PATH_add scripts/shell`** adds bare **`droplet`** for SSH to **`hermesuser`** (not the Hermes CLI hop).
- **Remote sudo password:** put **`SSH_SUDO_PASSWORD`** in the same **`~/.env/.env`** as **`SSH_*`**. Then **`hermes … droplet`** uses **`sudo -S`** on the server (no interactive sudo prompt). **`ssh_droplet.sh`** reattaches the inner command to **`/dev/tty`** after **`sudo -S`** so the Hermes TUI still sees a real terminal (piped sudo otherwise yields “Input is not a terminal” and an immediate exit). If unset, you type sudo on the **remote** TTY after SSH.
- **Automated / non-interactive remote steps** (git pull, scripts, smoke tests): **`./scripts/core/droplet_run.sh '…'`** (runs as **`SSH_USER`**, no sudo to **`hermesuser`** for that invocation only).
- **Interactive Hermes on the VPS** uses **`scripts/core/agent-droplet`**, which runs **`./venv/bin/python -m hermes_cli.main`** on the VPS and defaults **`HERMES_DROPLET_REQUIRE_SUDO=1`**. A prior **`droplet_run`** does not disable sudo for **`hermes … droplet`**.
- Lower-level control: **`scripts/core/ssh_droplet.sh`** header documents **`HERMES_DROPLET_REQUIRE_SUDO`**, **`--droplet-no-sudo`**, and **`~/.env/.env`** overrides.
- If **`~/.hermes/active_profile`** names a profile folder that does not exist (e.g. a mistaken **`droplet`** entry without **`~/.hermes/profiles/droplet`**), Hermes warns, removes the stale sticky file, and continues with the default home. The trailing **`droplet`** on **`hermes … droplet`** means “run on the VPS over SSH”, **not** “use a profile named droplet”. **`scripts/core/agent-droplet`** passes **`-p <your sticky profile name>`** on the server (same name as **`~/.hermes/active_profile`**, or **`chief-orchestrator`** if sticky is default/missing) so your **orchestrator** (or other) profile loads remotely — ensure that profile exists under **`/home/hermesuser/.hermes/profiles/`** on the VPS or set **`AGENT_DROPLET_PROFILE`** / **`AGENT_DROPLET_RUNTIME_HOME`**.

## Project Structure

```
hermes-agent/
├── run_agent.py          # AIAgent class — core conversation loop
├── model_tools.py        # Tool orchestration, _discover_tools(), handle_function_call()
├── toolsets.py           # Toolset definitions, _HERMES_CORE_TOOLS list
├── cli.py                # HermesCLI class — interactive CLI orchestrator
├── hermes_state.py       # SessionDB — SQLite session store (FTS5 search)
├── agent/                # Agent internals
│   ├── prompt_builder.py     # System prompt assembly
│   ├── context_compressor.py # Auto context compression
│   ├── prompt_caching.py     # Anthropic prompt caching
│   ├── auxiliary_client.py   # Auxiliary LLM client (vision, summarization)
│   ├── model_metadata.py     # Model context lengths, token estimation
│   ├── models_dev.py         # models.dev registry integration (provider-aware context)
│   ├── display.py            # KawaiiSpinner, tool preview formatting
│   ├── skill_commands.py     # Skill slash commands (shared CLI/gateway)
│   ├── turn_done_notify.py   # Optional HTTP ping when a root turn completes
│   ├── routing_canon.py      # Layered routing_canon.yaml loader + TurnRoutingIntent
│   ├── opm_quota_ladder.py   # OPM native OpenAI quota downgrade ladder (routing_canon)
│   ├── opm_cross_provider_failover.py  # OPM quota cascade: native → OpenRouter → fallback chain
│   ├── budget_ledger.py      # Daily spend file + AUD display (hard_budget canon)
│   ├── dynamic_routing_canon.yaml  # Repo defaults (overlay: HERMES_HOME/routing_canon.yaml)
│   └── trajectory.py         # Trajectory saving helpers
├── hermes_cli/           # CLI subcommands and setup
│   ├── main.py           # Entry point — all `hermes` subcommands
│   ├── config.py         # DEFAULT_CONFIG, OPTIONAL_ENV_VARS, migration
│   ├── commands.py       # Slash command definitions + SlashCommandCompleter
│   ├── callbacks.py      # Terminal callbacks (clarify, sudo, approval)
│   ├── setup.py          # Interactive setup wizard
│   ├── skin_engine.py    # Skin/theme engine — CLI visual customization
│   ├── skills_config.py  # `hermes skills` — enable/disable skills per platform
│   ├── tools_config.py   # `hermes tools` — enable/disable tools per platform
│   ├── skills_hub.py     # `/skills` slash command (search, browse, install)
│   ├── models.py         # Model catalog, provider model lists
│   ├── model_switch.py   # Shared /model switch pipeline (CLI + gateway)
│   └── auth.py           # Provider credential resolution
├── tools/                # Tool implementations (one file per tool)
│   ├── registry.py       # Central tool registry (schemas, handlers, dispatch)
│   ├── approval.py       # Dangerous command detection
│   ├── terminal_tool.py  # Terminal orchestration
│   ├── process_registry.py # Background process management
│   ├── file_tools.py     # File read/write/search/patch
│   ├── web_tools.py      # Web search/extract (Parallel + Firecrawl)
│   ├── browser_tool.py   # Browserbase browser automation
│   ├── code_execution_tool.py # execute_code sandbox
│   ├── delegate_tool.py  # Subagent delegation
│   ├── mcp_tool.py       # MCP client (~1050 lines)
│   └── environments/     # Terminal backends (local, docker, ssh, modal, daytona, singularity)
├── gateway/              # Messaging platform gateway
│   ├── run.py            # Main loop, slash commands, message dispatch
│   ├── session.py        # SessionStore — conversation persistence
│   └── platforms/        # Adapters: telegram, discord, slack, whatsapp, homeassistant, signal
├── acp_adapter/          # ACP server (VS Code / Zed / JetBrains integration)
├── cron/                 # Scheduler (jobs.py, scheduler.py)
├── environments/         # RL training environments (Atropos)
├── tests/                # Pytest suite (~3000 tests)
└── batch_runner.py       # Parallel batch processing
```

**User config:** `~/.hermes/config.yaml` (settings), `~/.hermes/.env` (API keys)

## File Dependency Chain

```
tools/registry.py  (no deps — imported by all tool files)
       ↑
tools/*.py  (each calls registry.register() at import time)
       ↑
model_tools.py  (imports tools/registry + triggers tool discovery)
       ↑
run_agent.py, cli.py, batch_runner.py, environments/
```

---

## AIAgent Class (run_agent.py)

```python
class AIAgent:
    def __init__(self,
        model: str = "anthropic/claude-opus-4.6",
        max_iterations: int = 90,
        enabled_toolsets: list = None,
        disabled_toolsets: list = None,
        quiet_mode: bool = False,
        save_trajectories: bool = False,
        platform: str = None,           # "cli", "telegram", etc.
        session_id: str = None,
        skip_context_files: bool = False,
        skip_memory: bool = False,
        # ... plus provider, api_mode, callbacks, routing params
    ): ...

    def chat(self, message: str) -> str:
        """Simple interface — returns final response string."""

    def run_conversation(self, user_message: str, system_message: str = None,
                         conversation_history: list = None, task_id: str = None) -> dict:
        """Full interface — returns dict with final_response + messages."""
```

### Agent Loop

The core loop is inside `run_conversation()` — entirely synchronous:

```python
while api_call_count < self.max_iterations and self.iteration_budget.remaining > 0:
    response = client.chat.completions.create(model=model, messages=messages, tools=tool_schemas)
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = handle_function_call(tool_call.name, tool_call.args, task_id)
            messages.append(tool_result_message(result))
        api_call_count += 1
    else:
        return response.content
```

Messages follow OpenAI format: `{"role": "system/user/assistant/tool", ...}`. Reasoning content is stored in `assistant_msg["reasoning"]`.

---

## CLI Architecture (cli.py)

- **Rich** for banner/panels, **prompt_toolkit** for input with autocomplete
- **KawaiiSpinner** (`agent/display.py`) — animated faces during API calls, `┊` activity feed for tool results
- `load_cli_config()` in cli.py merges hardcoded defaults + user config YAML
- **Skin engine** (`hermes_cli/skin_engine.py`) — data-driven CLI theming; initialized from `display.skin` config key at startup; skins customize banner colors, spinner faces/verbs/wings, tool prefix, response box, branding text
- `process_command()` is a method on `HermesCLI` — dispatches on canonical command name resolved via `resolve_command()` from the central registry
- Skill slash commands: `agent/skill_commands.py` scans `~/.hermes/skills/`, injects as **user message** (not system prompt) to preserve prompt caching

### Slash Command Registry (`hermes_cli/commands.py`)

All slash commands are defined in a central `COMMAND_REGISTRY` list of `CommandDef` objects. Every downstream consumer derives from this registry automatically:

- **CLI** — `process_command()` resolves aliases via `resolve_command()`, dispatches on canonical name
- **Gateway** — `GATEWAY_KNOWN_COMMANDS` frozenset for hook emission, `resolve_command()` for dispatch
- **Gateway help** — `gateway_help_lines()` generates `/help` output
- **Telegram** — `telegram_bot_commands()` generates the BotCommand menu
- **Slack** — `slack_subcommand_map()` generates `/hermes` subcommand routing
- **Autocomplete** — `COMMANDS` flat dict feeds `SlashCommandCompleter`
- **CLI help** — `COMMANDS_BY_CATEGORY` dict feeds `show_help()`

### Adding a Slash Command

1. Add a `CommandDef` entry to `COMMAND_REGISTRY` in `hermes_cli/commands.py`:
```python
CommandDef("mycommand", "Description of what it does", "Session",
           aliases=("mc",), args_hint="[arg]"),
```
2. Add handler in `HermesCLI.process_command()` in `cli.py`:
```python
elif canonical == "mycommand":
    self._handle_mycommand(cmd_original)
```
3. If the command is available in the gateway, add a handler in `gateway/run.py`:
```python
if canonical == "mycommand":
    return await self._handle_mycommand(event)
```
4. For persistent settings, use `save_config_value()` in `cli.py`

**CommandDef fields:**
- `name` — canonical name without slash (e.g. `"background"`)
- `description` — human-readable description
- `category` — one of `"Session"`, `"Configuration"`, `"Tools & Skills"`, `"Info"`, `"Exit"`
- `aliases` — tuple of alternative names (e.g. `("bg",)`)
- `args_hint` — argument placeholder shown in help (e.g. `"<prompt>"`, `"[name]"`)
- `cli_only` — only available in the interactive CLI
- `gateway_only` — only available in messaging platforms
- `gateway_config_gate` — config dotpath (e.g. `"display.tool_progress_command"`); when set on a `cli_only` command, the command becomes available in the gateway if the config value is truthy. `GATEWAY_KNOWN_COMMANDS` always includes config-gated commands so the gateway can dispatch them; help/menus only show them when the gate is open.

**Adding an alias** requires only adding it to the `aliases` tuple on the existing `CommandDef`. No other file changes needed — dispatch, help text, Telegram menu, Slack mapping, and autocomplete all update automatically.

---

## Adding New Tools

Requires changes in **3 files**:

**1. Create `tools/your_tool.py`:**
```python
import json, os
from tools.registry import registry

def check_requirements() -> bool:
    return bool(os.getenv("EXAMPLE_API_KEY"))

def example_tool(param: str, task_id: str = None) -> str:
    return json.dumps({"success": True, "data": "..."})

registry.register(
    name="example_tool",
    toolset="example",
    schema={"name": "example_tool", "description": "...", "parameters": {...}},
    handler=lambda args, **kw: example_tool(param=args.get("param", ""), task_id=kw.get("task_id")),
    check_fn=check_requirements,
    requires_env=["EXAMPLE_API_KEY"],
)
```

**2. Add import** in `model_tools.py` `_discover_tools()` list.

**3. Add to `toolsets.py`** — either `_HERMES_CORE_TOOLS` (all platforms) or a new toolset.

The registry handles schema collection, dispatch, availability checking, and error wrapping. All handlers MUST return a JSON string.

**Path references in tool schemas**: If the schema description mentions file paths (e.g. default output directories), use `display_hermes_home()` to make them profile-aware. The schema is generated at import time, which is after `_apply_profile_override()` sets `HERMES_HOME`.

**State files**: If a tool stores persistent state (caches, logs, checkpoints), use `get_hermes_home()` for the base directory — never `Path.home() / ".hermes"`. This ensures each profile gets its own state.

**Agent-level tools** (todo, memory): intercepted by `run_agent.py` before `handle_function_call()`. See `todo_tool.py` for the pattern.

---

## Adding Configuration

### config.yaml options:
1. Add to `DEFAULT_CONFIG` in `hermes_cli/config.py`
2. Bump `_config_version` (currently 28) to trigger migration for existing users

### .env variables:
1. Add to `OPTIONAL_ENV_VARS` in `hermes_cli/config.py` with metadata:
```python
"NEW_API_KEY": {
    "description": "What it's for",
    "prompt": "Display name",
    "url": "https://...",
    "password": True,
    "category": "tool",  # provider, tool, messaging, setting
},
```

### Config loaders (two separate systems):

| Loader | Used by | Location |
|--------|---------|----------|
| `load_cli_config()` | CLI mode | `cli.py` |
| `load_config()` | `hermes tools`, `hermes setup` | `hermes_cli/config.py` |
| Direct YAML load | Gateway | `gateway/run.py` |

---

## Skin/Theme System

The skin engine (`hermes_cli/skin_engine.py`) provides data-driven CLI visual customization. Skins are **pure data** — no code changes needed to add a new skin.

### Architecture

```
hermes_cli/skin_engine.py    # SkinConfig dataclass, built-in skins, YAML loader
~/.hermes/skins/*.yaml       # User-installed custom skins (drop-in)
```

- `init_skin_from_config()` — called at CLI startup, reads `display.skin` from config
- `get_active_skin()` — returns cached `SkinConfig` for the current skin
- `set_active_skin(name)` — switches skin at runtime (used by `/skin` command)
- `load_skin(name)` — loads from user skins first, then built-ins, then falls back to default
- Missing skin values inherit from the `default` skin automatically

### What skins customize

| Element | Skin Key | Used By |
|---------|----------|---------|
| Banner panel border | `colors.banner_border` | `banner.py` |
| Banner panel title | `colors.banner_title` | `banner.py` |
| Banner section headers | `colors.banner_accent` | `banner.py` |
| Banner dim text | `colors.banner_dim` | `banner.py` |
| Banner body text | `colors.banner_text` | `banner.py` |
| Response box border | `colors.response_border` | `cli.py` |
| Spinner faces (waiting) | `spinner.waiting_faces` | `display.py` |
| Spinner faces (thinking) | `spinner.thinking_faces` | `display.py` |
| Spinner verbs | `spinner.thinking_verbs` | `display.py` |
| Spinner wings (optional) | `spinner.wings` | `display.py` |
| Tool output prefix | `tool_prefix` | `display.py` |
| Per-tool emojis | `tool_emojis` | `display.py` → `get_tool_emoji()` |
| Agent name | `branding.agent_name` | `banner.py`, `cli.py` |
| Welcome message | `branding.welcome` | `cli.py` |
| Response box label | `branding.response_label` | `cli.py` |
| Prompt symbol | `branding.prompt_symbol` | `cli.py` |

### Built-in skins

- `default` — Classic Hermes gold/kawaii (the current look)
- `ares` — Crimson/bronze war-god theme with custom spinner wings
- `mono` — Clean grayscale monochrome
- `slate` — Cool blue developer-focused theme

### Adding a built-in skin

Add to `_BUILTIN_SKINS` dict in `hermes_cli/skin_engine.py`:

```python
"mytheme": {
    "name": "mytheme",
    "description": "Short description",
    "colors": { ... },
    "spinner": { ... },
    "branding": { ... },
    "tool_prefix": "┊",
},
```

### User skins (YAML)

Users create `~/.hermes/skins/<name>.yaml`:

```yaml
name: cyberpunk
description: Neon-soaked terminal theme

colors:
  banner_border: "#FF00FF"
  banner_title: "#00FFFF"
  banner_accent: "#FF1493"

spinner:
  thinking_verbs: ["jacking in", "decrypting", "uploading"]
  wings:
    - ["⟨⚡", "⚡⟩"]

branding:
  agent_name: "Cyber Agent"
  response_label: " ⚡ Cyber "

tool_prefix: "▏"
```

Activate with `/skin cyberpunk` or `display.skin: cyberpunk` in config.yaml.

---

## Remote VPS CLI (`hermes … droplet`)

For a **remote VPS runtime**, run the operator CLI exactly as you would locally, then append **`droplet` as the final token** (after all flags). Examples: `hermes tui droplet`, `hermes doctor droplet`, `hermes gateway watchdog-check droplet`. **Any** `hermes` subcommand works this way.

In deployment policy text, **“agent”** means this **operator CLI** (`hermes`), not a separate wrapper command.

Workstation setup: `.envrc` exports **`HERMES_REAL_BIN`** (real binary path) **before** **`PATH_add scripts/core`**, so `scripts/core/hermes` runs first and delegates to `scripts/core/agent-droplet` when the last argument is `droplet` (same delegation is implemented in **`hermes_cli.main`** for **`venv/bin/hermes`** / **`python -m hermes_cli.main`** when `scripts/core/agent-droplet` exists). By default **`ssh-agent`** / inherited **`SSH_ASKPASS`** are stripped; OpenSSH uses **`IdentityAgent=none`**, **`AddKeysToAgent=no`**, and on **macOS** **`UseKeychain=no`** so the login keychain cannot substitute for typing the **key passphrase**. Do not force **`PreferredAuthentications=publickey` only** — some **`sshd`** stacks require **publickey** then **keyboard-interactive** (PAM); locking to publickey leaves auth at “partial success”. Optional headless automation: add **`HERMES_DROPLET_ALLOW_ENV_PASSPHRASE=1`** as a **line in the same `~/.env/.env` file** as **`SSH_PASSPHRASE`** (a shell export alone does **not** enable this). The script uses a short-lived **`SSH_ASKPASS`** helper when you invoke **`scripts/core/ssh_droplet.sh` directly**. **`scripts/core/agent-droplet`** (the **`hermes … droplet`** path) **unsets** **`HERMES_DROPLET_ALLOW_ENV_PASSPHRASE`** so the SSH key passphrase is **not** auto-filled from the env file — you must enter it interactively (OpenSSH still uses **`IdentityAgent=none`**). **`agent-droplet`** sets **`HERMES_DROPLET_INTERACTIVE=1`** so the TTY check passes when an IDE has no tty on stdin. **`ssh_droplet.sh`** uses **`ssh -t`**, **`ControlMaster=no`**, and **`ControlPath=none`**: allocate a TTY for passphrase prompts in IDEs, and do **not** reuse a ControlPersist socket (which skips unlocking the key again). **`agent-droplet`** runs **`ssh_droplet`** under **`env -u HERMES_DROPLET_ALLOW_ENV_PASSPHRASE`** so a parent-exported env-file passphrase mode cannot apply. **`ssh_droplet_user.sh`** uses **interactive** **`sudo`** (you type the **sudo** password on the remote TTY; no pipe — piped **`sudo -S`** was closing the session). **`scripts/core/agent-droplet`** defaults to **`HERMES_HOME=.../profiles/chief-orchestrator`** on the server — create and select that profile once with **`./scripts/core/droplet_bootstrap_chief_orchestrator.sh`** (or **`./venv/bin/hermes profile create chief-orchestrator`** then **`./venv/bin/hermes profile use chief-orchestrator`**; **`profile switch`** is an alias for **`profile use`**). Put **`GEMINI_API_KEY`** (Google AI Studio) in that profile’s **`.env`** and set **`model.provider: gemini`** / **`model.default: gemini-2.5-flash`** (see `scripts/templates/chief-orchestrator-profile.example.yaml`). Canonical write-up: `policies/core/unified-deployment-and-security.md` Step 15.

## Important Policies
### Prompt Caching Must Not Break

Hermes-Agent ensures caching remains valid throughout a conversation. **Do NOT implement changes that would:**
- Alter past context mid-conversation
- Change toolsets mid-conversation
- Reload memories or rebuild system prompts mid-conversation

Cache-breaking forces dramatically higher costs. The ONLY time we alter context is during context compression.

### Manual `/models` picks vs OpenAI-primary mode (OPM)

`openai_primary_mode` in `config.yaml` can bias routing toward native OpenAI. A manual **`/models`** selection sets **`_defer_opm_primary_coercion`** so OPM **coercion** does not rewrite the chosen stack (including avoiding native **`api.openai.com`** for OpenRouter slugs like **`openai/gpt-5.4`**). **`manual_pipeline_forces_opm_bypass`** / **`HERMES_MANUAL_PIPELINE_BYPASS_OPM`** tune auxiliary behavior via **`manual_pipeline_opm_bypass_enabled()`**; they do **not** re-enable OPM coercion on manual picks. **Cheap-model routing** (`smart_model_routing` → short prompts sent to a small model such as Gemini Flash) is **not** applied while a sticky or one-shot pipeline pick is pending (CLI/gateway resolve the primary stack first, then merge). For manual pipeline agents, the **free_model_routing** provider fallback chain is cleared so failures do not hop Gemini → native GPT unless you re-enable fallbacks via config/env (see **`manual_pipeline_no_provider_fallback`**). Under **`openai_primary_mode`**: **`manual_pipeline_no_provider_fallback`** (default false; when true, `_try_activate_fallback` does not run for manual picks). Environment override: **`HERMES_MANUAL_PIPELINE_NO_PROVIDER_FALLBACK`**. For debugging wrong endpoint vs OpenRouter, set **`HERMES_PRE_LLM_ROUTING_TRACE=1`** or enable agent **`verbose_logging`** to emit a **`pre_llm_api_stack`** trace (includes **`base_url`**, **`opm_coercion_effective`**, **`opm_suppressed_turn`**, optional **`routing_canon_version`**). See **`agent/openai_primary_mode.py`** (`opm_coercion_effective`, `manual_pipeline_opm_bypass_enabled`).

### Routing canon (layered defaults + overlay)

- **Repo defaults:** `agent/dynamic_routing_canon.yaml` — versioned policy for consultant escalation knobs, **`openrouter/auto`** deliberation tiers, **operator gate** (Chief denial → `AIAgent.clarify_callback` in the CLI TUI), **`opm_native_quota_downgrade`** (ordered **`chat_models`** / **`codex_models`** on **`api.openai.com`**), **`opm_cross_provider_quota_failover`** (after the native ladder: OpenRouter **`openai/…`** list top-first, then **`openrouter/auto`**, then the **`free_model_routing` / `fallback_providers`** chain — Gemini, optional OpenRouter last resort, etc.), **`hard_budget`**, and routing-trace options.
- **Operator overlay:** `${HERMES_HOME}/routing_canon.yaml` — optional; **deep-merged** over the repo file (overlay wins on conflicts).
- **Loader:** `agent/routing_canon.py` — `load_merged_routing_canon()`, `merge_canon_into_consultant_routing()`, `build_turn_routing_intent(agent)` (per-turn snapshot on the agent as **`_turn_routing_intent`** after per-turn tier routing).
- **Consultant routing:** `agent/consultant_routing.py` merges the canon into the nested **`consultant_routing`** block from `workspace/operations/hermes_token_governance.runtime.yaml`. Manual **`/models`** (**`_defer_opm_primary_coercion`**) skips the operator gate; without **`clarify_callback`** (e.g. headless), Chief’s cap is kept and the gate is skipped (**DEBUG** log).
- **OPM vs rate limits:** With routing canon **`opm_native_quota_downgrade`** + **`opm_cross_provider_quota_failover`**, quota/rate-class errors run **`_try_opm_quota_cascade_step`** in the API retry loop: (1) native **`api.openai.com`** ladder (**`chat_models`** / **`codex_models`**), (2) OpenRouter explicit **`openrouter_*_models`** (requires **`OPENROUTER_API_KEY`**), (3) **`openrouter/auto`**, then (4) **`_try_activate_fallback`** through the configured fallback chain. OpenRouter hops set **`_opm_suppressed_for_turn`** and do **not** set **`_fallback_activated`** so **`_primary_runtime`** stays intact for the next user turn. **`_fallback_activated`** is set only when advancing the **`fallback_providers`** / free-routing chain. Credential-pool **429** recovery still defers cascade and fallback until the pool exhausts rotation when **`_opm_account_quota_exhaust_message`** is false.
- **Subprocess / delegation:** When OPM is on, **`agent/subprocess_governance.py`** unions **routing_canon** ladder slugs into **`_opm_effective_subprocess_allowlist_cores`** (so **`enforce_subprocess_model_policy`** / **`_is_openai_primary_mode_allowed`** treat them like other OPM-native subprocess models), and **`default_free_subprocess_model_id`** walks **`allowed_subprocess_models` → OPM defaults → ladder order → built-in primaries**.
- **Hard budget (`hard_budget` in routing canon):** Default **$10 AUD/day** (`daily_budget_aud` + `aud_to_usd` to map API USD estimates). **`reset_timezone`** (IANA, default **`Australia/Sydney`**) drives the budget bar “reset in …” countdown and the ledger’s calendar day on UTC VPS hosts. Persistent state: **`${HERMES_HOME}/workspace/operations/daily_budget_state.json`** (**`fcntl`** lock on POSIX when updating). Exceeding the cap triggers fallback like session budget. **CLI TUI:** bottom **`budget-bar`** shows turn cost, daily AUD/USD, hours to midnight in that zone. **`show_tui_bar: false`** hides the bar; per-turn totals still log at **DEBUG** from **`run_agent`**.

### Working Directory Behavior
- **CLI**: Uses current directory (`.` → `os.getcwd()`)
- **Messaging**: Uses `MESSAGING_CWD` env var (default: home directory)

### Background Process Notifications (Gateway)

When `terminal(background=true, check_interval=...)` is used, the gateway runs a watcher that
pushes status updates to the user's chat. Control verbosity with `display.background_process_notifications`
in config.yaml (or `HERMES_BACKGROUND_NOTIFICATIONS` env var):

- `all` — running-output updates + final message (default)
- `result` — only the final completion message
- `error` — only the final message when exit code != 0
- `off` — no watcher messages at all

### Turn-done notify (Mac sound over Tailscale)

Optional: when **`HERMES_TURN_DONE_NOTIFY_URL`** is set on the **runtime that finishes the turn** (e.g. droplet `~/.hermes/.env`), Hermes issues a fire-and-forget HTTP GET when each **root** `run_conversation` returns (including early exits from the API loop, not only the main success path). Does **not** run for delegate subagents. Point it at a tiny listener on your Mac — **outbound-only from the VPS**, no open ports on the server.

**Direct Tailscale (Mac must accept inbound on the tailnet):** **`tailscale ip -4`** on the Mac, run **`scripts/macos/hermes_turn_chime_server.py --bind 0.0.0.0 --port 8765`** in **Terminal.app** or **launchd** (IDE-only listeners often block non-localhost inbound). On the VPS: **`HERMES_TURN_DONE_NOTIFY_URL=http://<mac-tailscale-ip>:8765/`**. Verify from the VPS: **`curl -sS -o /dev/null -w '%{http_code}\n' http://<mac-tailscale-ip>:8765/`** → **`204`**. If that **times out**, the Mac is not listening or the path is blocked — use the tunnel below.

**SSH reverse tunnel (works when the VPS cannot open TCP to the Mac):** On the Mac, start the chime server on **`127.0.0.1:8765`**, then run **`scripts/macos/hermes_turn_chime_reverse_tunnel.sh user@vps`** (or `ssh -N -R 8765:127.0.0.1:8765 user@vps`). Keep that **`ssh` session** open (or use **autossh** / **launchd**). On the VPS set **`HERMES_TURN_DONE_NOTIFY_URL=http://127.0.0.1:8765/`** and **`gateway restart`**. The VPS then talks to **itself**; SSH carries the request to the Mac.

Default sound is **`Funk`** (`/System/Library/Sounds/Funk.aiff`); override with **`--sound`** or **`HERMES_TURN_DONE_SOUND`**. Optional **`HERMES_TURN_DONE_NOTIFY_TIMEOUT`** (default **8** seconds) adjusts the HTTP client timeout. Failures log at **WARNING** on the gateway (`turn_done_notify failed`).

### Gateway watchdog (production uptime)

External loops should use **`hermes gateway watchdog-check`** (see `gateway/status.py` → `runtime_status_watchdog_healthy`): it requires a **live `gateway.pid` process**, **`gateway_state=running`**, and messaging health — **default:** **≥1** platform **`connected`** in `gateway_state.json`; **strict (opt-in):** **`messaging.watchdog_require_all_platforms`** or **`HERMES_GATEWAY_WATCHDOG_REQUIRE_ALL_PLATFORMS`** so **every** configured platform is **`connected`**. The repo ships **`scripts/core/gateway-watchdog.sh`**, which defaults **`HERMES_HOME`** to **`profiles/chief-orchestrator`** when that directory exists, invokes Hermes via **`venv/bin/python -m hermes_cli.main -p …`**, and on failure prefers **`systemctl --user restart hermes-gateway-<profile>.service`** when installed (avoiding a second **`gateway run`** that steals platform locks), else **`gateway run --replace`**, then **`hermes doctor --fix`** + restart again if still unhealthy. Documented in **`website/docs/user-guide/messaging/gateway-watchdog.md`**.

**Second Mac / home-dir copy:** Token-scoped messaging locks live under **`$XDG_STATE_HOME/hermes/gateway-locks`** (or **`HERMES_GATEWAY_LOCK_DIR`**), not inside **`HERMES_HOME`**. Set **`HERMES_GATEWAY_LOCK_INSTANCE`** (e.g. **`mac-mini`**) in the Mac mini’s environment (launchd plist or shell profile) so lock files use a **host-specific subdirectory** and do not collide with another machine’s default path after copying state. **`gateway.pid`** / **`gateway_state.json`** stay profile-scoped via **`HERMES_HOME`**; the instance id is also recorded in those payloads when set. Running **two live gateways** with the **same** bot tokens still requires **different tokens** or **disabled** overlapping platforms—this env only isolates **local** lock files, not provider single-session rules.

---

## Profiles: Multi-Instance Support

Hermes supports **profiles** — multiple fully isolated instances, each with its own
`HERMES_HOME` directory (config, API keys, memory, sessions, skills, gateway, etc.).

The core mechanism: `_apply_profile_override()` in `hermes_cli/main.py` sets
`HERMES_HOME` before any module imports. All 119+ references to `get_hermes_home()`
automatically scope to the active profile.

### Profile wrapper aliases (`~/.local/bin/<name>`)

When you run **`hermes profile create …`** (without `--no-alias`) or **`hermes profile alias`**, Hermes installs a small script in **`~/.local/bin/`** so you can type **`coder chat`** instead of **`hermes -p coder chat`**.

Those wrappers **always run the agent from your repo virtualenv**: they **`exec`** **`$HERMES_AGENT_REPO/venv/bin/python`** (default **`$HOME/hermes-agent/venv/bin/python`**) with **`-m hermes_cli.main -p <profile>`**, not the global **`hermes`** on `PATH`. That avoids accidentally using a different install or dependencies.

- **`HERMES_AGENT_REPO`** — directory containing **`venv/`** (default: **`$HOME/hermes-agent`**).
- **`HERMES_VENV_PYTHON`** — optional full path to the interpreter (overrides the **`venv/bin/python`** derived from **`HERMES_AGENT_REPO`**).

If the venv path is missing, the wrapper prints an error and exits **`127`**. Ensure **`PATH`** includes **`~/.local/bin`** (see **`hermes profile create`** hints).

### Org roles and `delegate_task(hermes_profile=…)`

For **per-role tool and config isolation**, create named profiles from **`scripts/core/org_agent_profiles_manifest.yaml`** via **`./venv/bin/python scripts/core/bootstrap_org_agent_profiles.py`** (source profile defaults to **`chief-orchestrator`**). The chief (or any parent with the **delegation** toolset) can run a subagent under that profile using **`delegate_task`** with **`hermes_profile`** set to the profile name — **single-task only** (not combined with a multi-item **`tasks`** array). See **`scripts/templates/rem_operations/CHIEF_ORCHESTRATION_PLAYBOOK.md`** when materialized into **`HERMES_HOME/workspace/operations/`**.

### Rules for profile-safe code

1. **Use `get_hermes_home()` for all HERMES_HOME paths.** Import from `hermes_constants`.
   NEVER hardcode `~/.hermes` or `Path.home() / ".hermes"` in code that reads/writes state.
   ```python
   # GOOD
   from hermes_constants import get_hermes_home
   config_path = get_hermes_home() / "config.yaml"

   # BAD — breaks profiles
   config_path = Path.home() / ".hermes" / "config.yaml"
   ```

2. **Use `display_hermes_home()` for user-facing messages.** Import from `hermes_constants`.
   This returns `~/.hermes` for default or `~/.hermes/profiles/<name>` for profiles.
   ```python
   # GOOD
   from hermes_constants import display_hermes_home
   print(f"Config saved to {display_hermes_home()}/config.yaml")

   # BAD — shows wrong path for profiles
   print("Config saved to ~/.hermes/config.yaml")
   ```

3. **Module-level constants are fine** — they cache `get_hermes_home()` at import time,
   which is AFTER `_apply_profile_override()` sets the env var. Just use `get_hermes_home()`,
   not `Path.home() / ".hermes"`.

4. **Tests that mock `Path.home()` must also set `HERMES_HOME`** — since code now uses
   `get_hermes_home()` (reads env var), not `Path.home() / ".hermes"`:
   ```python
   with patch.object(Path, "home", return_value=tmp_path), \
        patch.dict(os.environ, {"HERMES_HOME": str(tmp_path / ".hermes")}):
       ...
   ```

5. **Gateway platform adapters should use token locks** — if the adapter connects with
   a unique credential (bot token, API key), call `acquire_scoped_lock()` from
   `gateway.status` in the `connect()`/`start()` method and `release_scoped_lock()` in
   `disconnect()`/`stop()`. This prevents two profiles from using the same credential.
   See `gateway/platforms/telegram.py` for the canonical pattern.

6. **Profile operations are HOME-anchored, not HERMES_HOME-anchored** — `_get_profiles_root()`
   returns `Path.home() / ".hermes" / "profiles"`, NOT `get_hermes_home() / "profiles"`.
   This is intentional — it lets `hermes -p coder profile list` see all profiles regardless
   of which one is active.

## Known Pitfalls

### DO NOT hardcode `~/.hermes` paths
Use `get_hermes_home()` from `hermes_constants` for code paths. Use `display_hermes_home()`
for user-facing print/log messages. Hardcoding `~/.hermes` breaks profiles — each profile
has its own `HERMES_HOME` directory. This was the source of 5 bugs fixed in PR #3575.

### DO NOT use `simple_term_menu` for interactive menus
Rendering bugs in tmux/iTerm2 — ghosting on scroll. Use `curses` (stdlib) instead. See `hermes_cli/tools_config.py` for the pattern.

### DO NOT use `\033[K` (ANSI erase-to-EOL) in spinner/display code
Leaks as literal `?[K` text under `prompt_toolkit`'s `patch_stdout`. Use space-padding: `f"\r{line}{' ' * pad}"`.

### `_last_resolved_tool_names` is a process-global in `model_tools.py`
`_run_single_child()` in `delegate_tool.py` saves and restores this global around subagent execution. If you add new code that reads this global, be aware it may be temporarily stale during child agent runs.

### DO NOT hardcode cross-tool references in schema descriptions
Tool schema descriptions must not mention tools from other toolsets by name (e.g., `browser_navigate` saying "prefer web_search"). Those tools may be unavailable (missing API keys, disabled toolset), causing the model to hallucinate calls to non-existent tools. If a cross-reference is needed, add it dynamically in `get_tool_definitions()` in `model_tools.py` — see the `browser_navigate` / `execute_code` post-processing blocks for the pattern.

### Tests must not write to `~/.hermes/`
The `_isolate_hermes_home` autouse fixture in `tests/conftest.py` redirects `HERMES_HOME` to a temp dir. Never hardcode `~/.hermes/` paths in tests.

**Profile tests**: When testing profile features, also mock `Path.home()` so that
`_get_profiles_root()` and `_get_default_hermes_home()` resolve within the temp dir.
Use the pattern from `tests/hermes_cli/test_profiles.py`:
```python
@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home
```

---

## Testing

```bash
source venv/bin/activate
python -m pytest tests/ -q          # Full suite (~3000 tests, ~3 min)
python -m pytest tests/test_model_tools.py -q   # Toolset resolution
python -m pytest tests/test_cli_init.py -q       # CLI config loading
python -m pytest tests/gateway/ -q               # Gateway tests
python -m pytest tests/tools/ -q                 # Tool-level tests
```

Always run the full suite before pushing changes.
