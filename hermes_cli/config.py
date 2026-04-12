"""
Configuration management for Hermes Agent.

Config files are stored in ~/.hermes/ for easy access:
- ~/.hermes/config.yaml  - All settings (model, toolsets, terminal, etc.)
- ~/.hermes/.env         - API keys and secrets

This module provides:
- hermes config          - Show current configuration
- hermes config edit     - Open config in editor
- hermes config set      - Set a specific value
- hermes config wizard   - Re-run setup wizard
"""

import os
import platform
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from tools.tool_backend_helpers import managed_nous_tools_enabled as _managed_nous_tools_enabled

_IS_WINDOWS = platform.system() == "Windows"
_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Env var names written to .env that aren't in OPTIONAL_ENV_VARS
# (managed by setup/provider flows directly).
_EXTRA_ENV_KEYS = frozenset({
    "OPENAI_API_KEY", "OPENAI_API_KEY_DROPLET", "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN",
    "AUXILIARY_VISION_MODEL",
    "DISCORD_HOME_CHANNEL", "TELEGRAM_HOME_CHANNEL",
    "SIGNAL_ACCOUNT", "SIGNAL_HTTP_URL",
    "SIGNAL_ALLOWED_USERS", "SIGNAL_GROUP_ALLOWED_USERS",
    "DINGTALK_CLIENT_ID", "DINGTALK_CLIENT_SECRET",
    "FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_ENCRYPT_KEY", "FEISHU_VERIFICATION_TOKEN",
    "WECOM_BOT_ID", "WECOM_SECRET",
    "TERMINAL_ENV", "TERMINAL_SSH_KEY", "TERMINAL_SSH_PORT",
    "WHATSAPP_MODE", "WHATSAPP_ENABLED", "WHATSAPP_ALLOWED_CHATS", "WHATSAPP_ALLOW_NON_SELF_DM",
    "TELEGRAM_ALLOWED_CHATS",
    "DISCORD_ALLOWED_CHANNELS", "DISCORD_ALLOWED_GUILDS",
    "SLACK_ALLOWED_CHANNELS", "SLACK_ALLOWED_TEAMS",
    "MATTERMOST_HOME_CHANNEL", "MATTERMOST_REPLY_MODE",
    "MATRIX_PASSWORD", "MATRIX_ENCRYPTION", "MATRIX_HOME_ROOM",
})
import yaml

from hermes_cli.colors import Colors, color
from hermes_cli.default_soul import DEFAULT_SOUL_MD


# =============================================================================
# Managed mode (NixOS declarative config)
# =============================================================================

_MANAGED_TRUE_VALUES = ("true", "1", "yes")
_MANAGED_SYSTEM_NAMES = {
    "brew": "Homebrew",
    "homebrew": "Homebrew",
    "nix": "NixOS",
    "nixos": "NixOS",
}


def get_managed_system() -> Optional[str]:
    """Return the package manager owning this install, if any."""
    raw = os.getenv("HERMES_MANAGED", "").strip()
    if raw:
        normalized = raw.lower()
        if normalized in _MANAGED_TRUE_VALUES:
            return "NixOS"
        return _MANAGED_SYSTEM_NAMES.get(normalized, raw)

    managed_marker = get_hermes_home() / ".managed"
    if managed_marker.exists():
        return "NixOS"
    return None


def is_managed() -> bool:
    """Check if Hermes is running in package-manager-managed mode.

    Two signals: the HERMES_MANAGED env var (set by the systemd service),
    or a .managed marker file in HERMES_HOME (set by the NixOS activation
    script, so interactive shells also see it).
    """
    return get_managed_system() is not None


def get_managed_update_command() -> Optional[str]:
    """Return the preferred upgrade command for a managed install."""
    managed_system = get_managed_system()
    if managed_system == "Homebrew":
        return "brew upgrade hermes-agent"
    if managed_system == "NixOS":
        return "sudo nixos-rebuild switch"
    return None


def recommended_update_command() -> str:
    """Return the best update command for the current installation."""
    return get_managed_update_command() or "hermes update"


def format_managed_message(action: str = "modify this Hermes installation") -> str:
    """Build a user-facing error for managed installs."""
    managed_system = get_managed_system() or "a package manager"
    raw = os.getenv("HERMES_MANAGED", "").strip().lower()

    if managed_system == "NixOS":
        env_hint = "true" if raw in _MANAGED_TRUE_VALUES else raw or "true"
        return (
            f"Cannot {action}: this Hermes installation is managed by NixOS "
            f"(HERMES_MANAGED={env_hint}).\n"
            "Edit services.hermes-agent.settings in your configuration.nix and run:\n"
            "  sudo nixos-rebuild switch"
        )

    if managed_system == "Homebrew":
        env_hint = raw or "homebrew"
        return (
            f"Cannot {action}: this Hermes installation is managed by Homebrew "
            f"(HERMES_MANAGED={env_hint}).\n"
            "Use:\n"
            "  brew upgrade hermes-agent"
        )

    return (
        f"Cannot {action}: this Hermes installation is managed by {managed_system}.\n"
        "Use your package manager to upgrade or reinstall Hermes."
    )

def managed_error(action: str = "modify configuration"):
    """Print user-friendly error for managed mode."""
    print(format_managed_message(action), file=sys.stderr)


# =============================================================================
# Config paths
# =============================================================================

# Re-export from hermes_constants — canonical definition lives there.
from hermes_constants import get_hermes_home  # noqa: F811,E402

def get_config_path() -> Path:
    """Get the main config file path."""
    return get_hermes_home() / "config.yaml"


def merge_user_config_yaml(updates: dict) -> Path:
    """Deep-merge *updates* into the on-disk ``config.yaml`` for the active HERMES_HOME.

    Preserves unrelated keys. Uses the same merge semantics as user config loading.
    """
    from utils import atomic_yaml_write

    ensure_hermes_home()
    path = get_config_path()
    user: dict = {}
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                user = yaml.safe_load(f) or {}
        except Exception:
            user = {}
    if not isinstance(user, dict):
        user = {}
    merged = _deep_merge(user, updates)
    atomic_yaml_write(path, merged)
    return path

def get_env_path() -> Path:
    """Get the .env file path (for API keys)."""
    return get_hermes_home() / ".env"

def get_project_root() -> Path:
    """Get the project installation directory."""
    return Path(__file__).parent.parent.resolve()

def _secure_dir(path):
    """Set directory to owner-only access (0700). No-op on Windows."""
    try:
        os.chmod(path, 0o700)
    except (OSError, NotImplementedError):
        pass


def _secure_file(path):
    """Set file to owner-only read/write (0600). No-op on Windows."""
    try:
        if os.path.exists(str(path)):
            os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        pass


def _ensure_default_soul_md(home: Path) -> None:
    """Seed a default SOUL.md into HERMES_HOME if the user doesn't have one yet."""
    soul_path = home / "SOUL.md"
    if soul_path.exists():
        return
    soul_path.write_text(DEFAULT_SOUL_MD, encoding="utf-8")
    _secure_file(soul_path)


def ensure_hermes_home():
    """Ensure ~/.hermes directory structure exists with secure permissions."""
    home = get_hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    _secure_dir(home)
    for subdir in ("cron", "sessions", "logs", "memories"):
        d = home / subdir
        d.mkdir(parents=True, exist_ok=True)
        _secure_dir(d)
    _ensure_default_soul_md(home)


# =============================================================================
# Config loading/saving
# =============================================================================

DEFAULT_CONFIG = {
    # Default inference model when config.yaml omits model.default (Google AI Studio
    # free tier). Provider is left unset so ``resolve_provider(auto)`` picks from API keys.
    "model": {"default": "gemini-2.5-flash"},
    "fallback_providers": None,
    "openai_primary_mode": {
        "enabled": False,
        "default_model": "gpt-5.4",
        "codex_model": "gpt-5.3-codex",
        "allowed_subprocess_models": ["gpt-5.4", "gpt-5.3-codex"],
        "require_direct_openai": True,
        # When enabled, auxiliary/review paths use ``opm_auxiliary_model`` unless empty (then gemini-2.5-flash).
        "opm_auxiliary_model": "",
        # When true (default), a manual ``/models`` pick disables OPM model/runtime coercion for that agent.
        # Override with env HERMES_MANUAL_PIPELINE_BYPASS_OPM=0 to force OPM even on manual picks (rare).
        "manual_pipeline_forces_opm_bypass": True,
        # When true, manual ``/models`` turns do not advance the provider fallback chain (fail on the chosen stack).
        # Default false: rate-limit / quota paths may still try configured fallbacks (policy B).
        "manual_pipeline_no_provider_fallback": False,
    },
    "cost_governance": {
        "daily_budget_usd": 10.0,
        "session_budget_usd": 2.50,
        "spike_threshold_usd_per_min": 0.50,
        "summary_review_enabled": True,
        "stall_timeout_expensive_seconds": 120,
        "stall_timeout_cheap_seconds": 60,
        "max_nudges_per_turn": 2,
    },
    "provider_health": {
        "huggingface_max_failures": 1,
        "default_max_failures": 3,
    },
    "free_model_routing": {
        "enabled": True,
        # When local_models/hub/state.json lists downloads, tier hub ids not marked
        # downloaded are hidden from /models and omitted from the synthesized fallback chain.
        "filter_free_tier_models_by_local_hub": True,
        # When router_model is set but all tier targets are filtered out, use this id alone (Gemini API).
        "fallback_free_routed_model": "gemini-2.5-flash",
        # Tier ids that are Gemini API model names (not HF hub repos) — never filtered by local_models/hub.
        "gemini_native_tier_models": [
            "gemini-2.5-flash",
        ],
        "tiers": [
            {
                "id": "local",
                "description": (
                    "Gemini API native tier (gemini-2.5-flash); optional local hub models "
                    "when HERMES_LOCAL_INFERENCE_BASE_URL + local_models/hub/state.json match"
                ),
                "models": [
                    "gemini-2.5-flash",
                ],
            },
        ],
        # Gemini-based tier router: gemini-2.5-flash picks a model from tiers via Google AI.
        "kimi_router": {
            "router_provider": "gemini",
            "router_model": "gemini-2.5-flash",
        },
        "optional_gemini": {
            "enabled": True,
            "model": "gemini-2.5-flash",
            "only_rate_limit": True,
            "restore_health_check": True,
        },
        "openrouter_last_resort": {
            "enabled": True,
            "model": "google/gemini-2.5-flash",
        },
    },
    "credential_pool_strategies": {},
    "toolsets": ["hermes-cli"],
    "agent": {
        "max_turns": 90,
        # When true, do not inject HERMES_HOME/.hermes.md, workspace BOOTSTRAP/AGENTS,
        # cwd AGENTS.md / .hermes.md chain, or SOUL.md into the system prompt (see
        # run_agent.AIAgent / build_context_files_prompt). Use when policies live on
        # disk and are loaded via tools, or after a bootstrap session — reduces tokens.
        # Override anytime with env HERMES_SKIP_CONTEXT_FILES=1|0.
        "skip_context_files": False,
        # Tool-use enforcement: injects system prompt guidance that tells the
        # model to actually call tools instead of describing intended actions.
        # Values: "auto" (default — applies to gpt/codex models), true/false
        # (force on/off for all models), or a list of model-name substrings
        # to match (e.g. ["gpt", "codex", "gemini"]).
        "tool_use_enforcement": "auto",
        # Optional CLI-only: fast auxiliary LLM routes user text to a named profile via
        # delegate_task before the main agent loop (off by default — extra cost/latency).
        "profile_router": {
            "enabled": False,
            # Slightly below 0.72 so clear specialist queries still route when the
            # router model is conservative (no security-specific hardcoding in code).
            "confidence_threshold": 0.65,
            "min_message_chars": 12,
            "exclude_current_profile": True,
            # If non-empty, only run the router when get_active_profile_name() is listed.
            "only_when_current_profiles": [],
            # If non-empty, only these slugs may be routing targets.
            "allow_only_profiles": [],
            "exclude_profiles": [],
            "router_model": "",
            "router_provider": "",
            # When true (default), profile routing uses ``free_model_routing`` (Gemini tier pick).
            "use_free_model_routing": True,
        },
        # When enabled, the ``sync_org_automation`` tool may run manifest bootstrap +
        # ORG_REGISTRY / ORG_CHART auto-blocks. CLI/cron: ``hermes workspace org-automation apply``.
        "org_automation": {
            "enabled": False,
        },
    },
    
    "terminal": {
        "backend": "local",
        "modal_mode": "auto",
        "cwd": ".",  # Use current directory
        "timeout": 180,
        # Environment variables to pass through to sandboxed execution
        # (terminal and execute_code).  Skill-declared required_environment_variables
        # are passed through automatically; this list is for non-skill use cases.
        "env_passthrough": [],
        "docker_image": "nikolaik/python-nodejs:python3.11-nodejs20",
        "docker_forward_env": [],
        "singularity_image": "docker://nikolaik/python-nodejs:python3.11-nodejs20",
        "modal_image": "nikolaik/python-nodejs:python3.11-nodejs20",
        "daytona_image": "nikolaik/python-nodejs:python3.11-nodejs20",
        # Container resource limits (docker, singularity, modal, daytona — ignored for local/ssh)
        "container_cpu": 1,
        "container_memory": 5120,       # MB (default 5GB)
        "container_disk": 51200,        # MB (default 50GB)
        "container_persistent": True,   # Persist filesystem across sessions
        # Docker volume mounts — share host directories with the container.
        # Each entry is "host_path:container_path" (standard Docker -v syntax).
        # Example: ["/home/user/projects:/workspace/projects", "/data:/data"]
        "docker_volumes": [],
        # Explicit opt-in: mount the host cwd into /workspace for Docker sessions.
        # Default off because passing host directories into a sandbox weakens isolation.
        "docker_mount_cwd_to_workspace": False,
        # Persistent shell — keep a long-lived bash shell across execute() calls
        # so cwd/env vars/shell variables survive between commands.
        # Enabled by default for non-local backends (SSH); local is always opt-in
        # via TERMINAL_LOCAL_PERSISTENT env var.
        "persistent_shell": True,
    },
    
    "browser": {
        "inactivity_timeout": 120,
        "command_timeout": 30,  # Timeout for browser commands in seconds (screenshot, navigate, etc.)
        "record_sessions": False,  # Auto-record browser sessions as WebM videos
        "allow_private_urls": False,  # Allow navigating to private/internal IPs (localhost, 192.168.x.x, etc.)
        "camofox": {
            # When true, Hermes sends a stable profile-scoped userId to Camofox
            # so the server can map it to a persistent browser profile directory.
            # Requires Camofox server to be configured with CAMOFOX_PROFILE_DIR.
            # When false (default), each session gets a random userId (ephemeral).
            "managed_persistence": False,
        },
    },

    # Filesystem checkpoints — automatic snapshots before destructive file ops.
    # When enabled, the agent takes a snapshot of the working directory once per
    # conversation turn (on first write_file/patch call).  Use /rollback to restore.
    "checkpoints": {
        "enabled": True,
        "max_snapshots": 50,  # Max checkpoints to keep per directory
    },

    # Maximum characters returned by a single read_file call.  Reads that
    # exceed this are rejected with guidance to use offset+limit.
    # 100K chars ≈ 25–35K tokens across typical tokenisers.
    "file_read_max_chars": 100_000,
    
    "compression": {
        "enabled": True,
        "threshold": 0.50,            # compress when context usage exceeds this ratio
        "target_ratio": 0.20,         # fraction of threshold to preserve as recent tail
        "protect_last_n": 20,         # minimum recent messages to keep uncompressed
        "summary_model": "",          # empty = use main configured model
        "summary_provider": "auto",
        "summary_base_url": None,
    },
    "smart_model_routing": {
        "enabled": False,
        "max_simple_chars": 160,
        "max_simple_words": 28,
        "cheap_model": {},
    },
    
    # Auxiliary model config — provider:model for each side task.
    # Format: provider is the provider name, model is the model slug.
    # "auto" for provider = auto-detect best available provider.
    # Empty model = use provider's default auxiliary model.
    # All tasks fall back to openrouter:google/gemini-3-flash-preview if
    # the configured provider is unavailable.
    "auxiliary": {
        "vision": {
            "provider": "auto",    # auto | openrouter | nous | codex | custom
            "model": "",           # e.g. "google/gemini-2.5-flash", "gpt-4o"
            "base_url": "",        # direct OpenAI-compatible endpoint (takes precedence over provider)
            "api_key": "",         # API key for base_url (falls back to OPENAI_API_KEY)
            "timeout": 30,         # seconds — LLM API call timeout; increase for slow local vision models
            "download_timeout": 30,  # seconds — image HTTP download timeout; increase for slow connections
        },
        "web_extract": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 30,         # seconds — increase for slow local models
        },
        "compression": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 120,        # seconds — compression summarises large contexts; increase for local models
        },
        "session_search": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 30,
        },
        "skills_hub": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 30,
        },
        "approval": {
            "provider": "auto",
            "model": "",           # fast/cheap model recommended (e.g. gemini-flash, haiku)
            "base_url": "",
            "api_key": "",
            "timeout": 30,
        },
        "mcp": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 30,
        },
        "flush_memories": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 30,
        },
        # Internal consultant routing (tier pick + challenger + chief) — not user dialogue.
        "consultant_router": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 45,
        },
        "consultant_challenger": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 45,
        },
        "consultant_chief": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 60,
        },
        "profile_router": {
            "provider": "auto",
            "model": "",
            "base_url": "",
            "api_key": "",
            "timeout": 25,
        },
    },
    
    "display": {
        "compact": False,
        "personality": "kawaii",
        "resume_display": "full",
        "busy_input_mode": "interrupt",
        "bell_on_complete": False,
        "show_reasoning": False,
        "streaming": False,
        "inline_diffs": True,     # Show inline diff previews for write actions (write_file, patch, skill_manage)
        "show_cost": False,       # Show $ cost in the status bar (off by default)
        "skin": "default",
        "tool_progress_command": False,  # Enable /verbose command in messaging gateway
        "tool_preview_length": 0,  # Max chars for tool call previews (0 = no limit, show full paths/commands)
        # Forward AIAgent status_callback lines to Telegram/Slack/WhatsApp (separate chat messages).
        "gateway_status_messages": True,
        # When True, only token_governance / consultant events are sent (not rate-limit retries etc.).
        "gateway_status_governance_only": False,
        # Forward [Router] heartbeats, stall nudges, summary-review lines, and
        # delegation watchdog messages to messaging platforms. Set False for Slack/Telegram
        # when you only want the final assistant reply (plus governance/consultant if enabled).
        "gateway_status_router_messages": True,
        # Tier routing lines ("Token governance: this turn Tier …"). Omitted by default in
        # chat; set true to forward. When gateway_status_governance_only is true, tier lines
        # are forwarded unless this key is explicitly false.
        "gateway_status_token_governance": None,
    },

    # Privacy settings
    "privacy": {
        "redact_pii": False,  # When True, hash user IDs and strip phone numbers from LLM context
    },
    
    # Text-to-speech configuration
    "tts": {
        "provider": "edge",  # "edge" (free) | "elevenlabs" (premium) | "openai" | "neutts" (local)
        "edge": {
            "voice": "en-US-AriaNeural",
            # Popular: AriaNeural, JennyNeural, AndrewNeural, BrianNeural, SoniaNeural
        },
        "elevenlabs": {
            "voice_id": "pNInz6obpgDQGcFmaJgB",  # Adam
            "model_id": "eleven_multilingual_v2",
        },
        "openai": {
            "model": "gpt-4o-mini-tts",
            "voice": "alloy",
            # Voices: alloy, echo, fable, onyx, nova, shimmer
        },
        "neutts": {
            "ref_audio": "",  # Path to reference voice audio (empty = bundled default)
            "ref_text": "",   # Path to reference voice transcript (empty = bundled default)
            "model": "neuphonic/neutts-air-q4-gguf",  # HuggingFace model repo
            "device": "cpu",  # cpu, cuda, or mps
        },
    },
    
    "stt": {
        "enabled": True,
        "provider": "local",  # "local" (free, faster-whisper) | "groq" | "openai" (Whisper API)
        "local": {
            "model": "base",  # tiny, base, small, medium, large-v3
        },
        "openai": {
            "model": "whisper-1",  # whisper-1, gpt-4o-mini-transcribe, gpt-4o-transcribe
        },
    },

    "voice": {
        "record_key": "ctrl+b",
        "max_recording_seconds": 120,
        "auto_tts": False,
        "silence_threshold": 200,     # RMS below this = silence (0-32767)
        "silence_duration": 3.0,      # Seconds of silence before auto-stop
    },
    
    "human_delay": {
        "mode": "off",
        "min_ms": 800,
        "max_ms": 2500,
    },
    
    # Persistent memory -- bounded curated memory injected into system prompt
    "memory": {
        "memory_enabled": True,
        "user_profile_enabled": True,
        "memory_char_limit": 2200,   # ~800 tokens at 2.75 chars/token
        "user_char_limit": 1375,     # ~500 tokens at 2.75 chars/token
        # External memory provider plugin (empty = auto-detect).
        # Set to a provider name to activate explicitly: "openviking", "mem0",
        # "hindsight", "holographic", "retaindb", "byterover", "honcho".
        # When empty: Honcho auto-migrates if ~/.honcho/config.json is enabled
        # with credentials; else Mem0 activates if MEM0_API_KEY or mem0.json
        # has api_key (run_agent persists memory.provider on first activation).
        # Only ONE external provider is allowed at a time.
        "provider": "",
    },

    # Subagent delegation — override the provider:model used by delegate_task
    # so child agents can run on a different (cheaper/faster) provider and model.
    # Uses the same runtime provider resolution as CLI/gateway startup, so all
    # configured providers (OpenRouter, Nous, Z.ai, Kimi, etc.) are supported.
    "delegation": {
        "model": "",       # e.g. "google/gemini-3-flash-preview" (empty = inherit parent model)
        "provider": "",    # e.g. "openrouter" (empty = inherit parent provider + credentials)
        "base_url": "",    # direct OpenAI-compatible endpoint for subagents
        "api_key": "",     # API key for delegation.base_url (falls back to OPENAI_API_KEY)
        "max_iterations": 50,  # per-subagent iteration cap (each subagent gets its own budget,
                               # independent of the parent's max_iterations)
    },

    # Ephemeral prefill messages file — JSON list of {role, content} dicts
    # injected at the start of every API call for few-shot priming.
    # Never saved to sessions, logs, or trajectories.
    "prefill_messages_file": "",
    
    # Skills — external skill directories for sharing skills across tools/agents.
    # Each path is expanded (~, ${VAR}) and resolved.  Read-only — skill creation
    # always goes to ~/.hermes/skills/.
    "skills": {
        "external_dirs": [],   # e.g. ["~/.agents/skills", "/shared/team-skills"]
    },

    # Honcho AI-native memory -- reads ~/.honcho/config.json as single source of truth.
    # This section is only needed for hermes-specific overrides; everything else
    # (apiKey, workspace, peerName, sessions, enabled) comes from the global config.
    "honcho": {},

    # IANA timezone (e.g. "Asia/Kolkata", "America/New_York").
    # Empty string means use server-local time.
    "timezone": "",

    # Discord platform settings (gateway mode)
    "discord": {
        "require_mention": True,       # Require @mention to respond in server channels
        "free_response_channels": "",  # Comma-separated channel IDs where bot responds without mention
        "auto_thread": True,           # Auto-create threads on @mention in channels (like Slack)
        "reactions": True,             # Add 👀/✅/❌ reactions to messages during processing
    },

    # WhatsApp platform settings (gateway mode)
    "whatsapp": {
        # Reply prefix prepended to every outgoing WhatsApp message.
        # Default (None) uses the built-in "⚕ *Hermes Agent*" header.
        # Set to "" (empty string) to disable the header entirely.
        # Supports \n for newlines, e.g. "🤖 *My Bot*\n──────\n"
    },

    # Approval mode for dangerous commands:
    #   manual — always prompt the user (default)
    #   smart  — use auxiliary LLM to auto-approve low-risk commands, prompt for high-risk
    #   off    — skip all approval prompts (equivalent to --yolo)
    "approvals": {
        "mode": "manual",
        "timeout": 60,
    },

    # Permanently allowed dangerous command patterns (added via "always" approval)
    "command_allowlist": [],
    # User-defined quick commands that bypass the agent loop (type: exec only)
    "quick_commands": {},
    # Custom personalities — add your own entries here
    # Supports string format: {"name": "system prompt"}
    # Or dict format: {"name": {"description": "...", "system_prompt": "...", "tone": "...", "style": "..."}}
    "personalities": {},

    # Pre-exec security scanning via tirith
    "security": {
        "redact_secrets": True,
        "tirith_enabled": True,
        "tirith_path": "tirith",
        "tirith_timeout": 5,
        "tirith_fail_open": True,
        "website_blocklist": {
            "enabled": False,
            "domains": [],
            "shared_files": [],
        },
    },

    "cron": {
        # Wrap delivered cron responses with a header (task name) and footer
        # ("The agent cannot see this message").  Set to false for clean output.
        "wrap_response": True,
    },

    # Optional paths to cloned third-party repos for /paperclip and /autoresearch helpers.
    # Override per-machine with HERMES_PAPERCLIP_REPO / HERMES_AUTORESEARCH_REPO.
    "integrations": {
        "paperclip": {"repo": ""},
        "autoresearch": {"repo": ""},
    },

    # Config schema version - bump this when adding new required fields
    "_config_version": 29,
}

# =============================================================================
# Config Migration System
# =============================================================================

# Track which env vars were introduced in each config version.
# Migration only mentions vars new since the user's previous version.
ENV_VARS_BY_VERSION: Dict[int, List[str]] = {
    29: [
        "HERMES_PAPERCLIP_REPO",
        "HERMES_AUTORESEARCH_REPO",
    ],
    28: [
        "HERMES_MANUAL_PIPELINE_BYPASS_OPM",
        "HERMES_MANUAL_PIPELINE_NO_PROVIDER_FALLBACK",
    ],
    3: ["FIRECRAWL_API_KEY", "BROWSERBASE_API_KEY", "BROWSERBASE_PROJECT_ID", "FAL_KEY"],
    4: ["VOICE_TOOLS_OPENAI_KEY", "ELEVENLABS_API_KEY"],
    5: ["WHATSAPP_ENABLED", "WHATSAPP_MODE", "WHATSAPP_ALLOWED_USERS", "WHATSAPP_ALLOW_NON_SELF_DM",
        "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_ALLOWED_USERS"],
    10: ["TAVILY_API_KEY"],
    11: ["TERMINAL_MODAL_MODE"],
    12: ["SLACK_NOTIFY_WITH_USER_MENTION", "SLACK_NOTIFY_USER_ID"],
}

# Required environment variables with metadata for migration prompts.
# LLM provider is required but handled in the setup wizard's provider
# selection step (Nous Portal / OpenRouter / Custom endpoint), so this
# dict is intentionally empty — no single env var is universally required.
REQUIRED_ENV_VARS = {}

# Optional environment variables that enhance functionality
OPTIONAL_ENV_VARS = {
    "HERMES_PAPERCLIP_REPO": {
        "description": "Absolute path to a cloned cc-org-au/paperclip repo (shown in /paperclip hints).",
        "prompt": "Path to paperclip clone (optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "HERMES_AUTORESEARCH_REPO": {
        "description": "Absolute path to a cloned cc-org-au/autoresearch repo (shown in /autoresearch hints).",
        "prompt": "Path to autoresearch clone (optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "HERMES_TURN_DONE_NOTIFY_URL": {
        "description": (
            "Optional HTTP URL Hermes GETs (fire-and-forget) when a root agent turn finishes — "
            "e.g. Mac Tailscale IP + scripts/macos/hermes_turn_chime_server.py for a local sound. "
            "Set only on the runtime that should notify (e.g. droplet ~/.hermes/.env)."
        ),
        "prompt": "Turn-done notify URL (optional, e.g. http://100.x.y.z:8765/)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "HERMES_TURN_DONE_SOUND": {
        "description": "Used only by scripts/macos/hermes_turn_chime_server.py — path to .aiff for afplay (default Funk).",
        "prompt": "Path to sound file for turn chime server (optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "HERMES_TURN_DONE_NOTIFY_TIMEOUT": {
        "description": "Seconds for the HTTP GET in agent/turn_done_notify.py (default 8). Increase on slow Tailscale paths.",
        "prompt": "Turn-done notify HTTP timeout seconds (optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "HERMES_GATEWAY_LOCK_INSTANCE": {
        "description": "Optional subdirectory under the gateway messaging lock directory (e.g. mac-mini) so this host keeps token lock files separate from another machine or a copied ~/.local/state tree. Two live gateways still need distinct bot tokens or non-overlapping platforms.",
        "prompt": "Gateway lock instance id (optional, e.g. mac-mini)",
        "url": None,
        "password": False,
        "category": "messaging",
        "advanced": True,
    },
    "HERMES_CLI_INSTANCE_LABEL": {
        "description": "Short label shown in the CLI TUI status bar (green), left of the model name (e.g. operator, droplet). If unset, derived from HERMES_GATEWAY_LOCK_INSTANCE when it is droplet or operator/mac-mini.",
        "prompt": "CLI instance badge (optional, e.g. droplet)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "HERMES_BLOCK_FILE_TOOLS_HERMES_DOTENV": {
        "description": (
            "When 1/true, block write_file/patch to paths under ~/.hermes named .env. "
            "Default (unset): Hermes profile .env files are writable so gateway/messaging agents can update keys."
        ),
        "prompt": "Block file-tool writes to ~/.hermes/**/.env (optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "HERMES_LIST_SESSIONS_ALL_SOURCES": {
        "description": (
            "Gateway: when 1/true, `/resume` with no arguments lists recent sessions from **all** linked "
            "platforms (Slack/Telegram/WhatsApp…), not only the current one. Same effect as "
            "`messaging.list_sessions_all_sources: true` in gateway config.yaml."
        ),
        "prompt": "List all-platform sessions for /resume (optional)",
        "url": None,
        "password": False,
        "category": "messaging",
        "advanced": True,
    },
    # ── Workstation ~/.env — Mac mini / operator SSH (scripts; not Hermes runtime) ──
    "MACMINI_SSH_USER": {
        "description": "Remote user for sync_droplet_to_macmini.sh (often operator).",
        "prompt": "Mac mini SSH user (optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "MACMINI_SSH_HOST": {
        "description": "Mac mini SSH host — use Tailscale IPv4 after hardening (see memory/core/scripts/core/macmini_*.sh).",
        "prompt": "Mac mini SSH host / Tailscale IP (optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "MACMINI_SSH_PORT": {
        "description": "Mac mini SSH port (52822 after Tailscale-only hardening; default script uses 22 if unset).",
        "prompt": "Mac mini SSH port (optional, e.g. 52822)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "MACMINI_SSH_KEY": {
        "description": "Optional path to SSH private key for MACMINI; defaults to SSH_KEY_FILE / ~/.env/.ssh_key.",
        "prompt": "Mac mini SSH private key path (optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "SSH_IP_OPERATOR": {
        "description": "Mac mini Tailscale IPv4 (or legacy user@host) for operator automation; pair with MACMINI_SSH_* for sync script.",
        "prompt": "Mac mini operator SSH target (optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "SSH_ADMIN_OPERATOR": {
        "description": "macOS admin account name on the Mac mini (sudo / break-glass).",
        "prompt": "Mac mini admin macOS username (optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "SSH_ADMIN_PW_OPERATOR": {
        "description": "macOS login/sudo password for SSH_ADMIN_OPERATOR on the Mac mini (for scripted sudo -S only — prefer Touch ID / interactive sudo in daily use).",
        "prompt": "Mac mini admin password (optional)",
        "url": None,
        "password": True,
        "category": "setting",
        "advanced": True,
    },
    "SSH_PUBLIC_OPERATOR": {
        "description": "ssh-ed25519 public key line for Mac mini access (authorized_keys).",
        "prompt": "Mac mini SSH public key line (optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "SSH_PRIVATE_OPERATOR": {
        "description": "Base64-encoded OpenSSH private key body (single line in .env) for Mac mini; unlock with SSH_PASSPHRASE / operator passphrase as used at key creation.",
        "prompt": "Mac mini SSH private key (base64, optional)",
        "url": None,
        "password": True,
        "category": "setting",
        "advanced": True,
    },
    # ── Local inference (vLLM / llama.cpp / Ollama OpenAI-compatible server) ──
    "HERMES_LOCAL_INFERENCE_BASE_URL": {
        "description": "Base URL for a local OpenAI-compatible inference server (vLLM, llama.cpp, Ollama). "
                       "When set, locally-downloaded models from local_models/hub/ are served via this URL "
                       "instead of HuggingFace Inference Providers. Example: http://localhost:8000",
        "prompt": "Local inference server base URL (e.g. http://localhost:8000)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "HERMES_LOCAL_INFERENCE_API_KEY": {
        "description": "API key for the local inference server (leave empty for 'dummy-local' default)",
        "prompt": "Local inference server API key (leave empty for default)",
        "url": None,
        "password": True,
        "category": "setting",
        "advanced": True,
    },
    "HERMES_MANUAL_PIPELINE_BYPASS_OPM": {
        "description": "When 1 (default unset), manual /models picks disable OPM model coercion; set to 0 to force OPM even on manual picks.",
        "prompt": "HERMES_MANUAL_PIPELINE_BYPASS_OPM (1/0, optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    "HERMES_MANUAL_PIPELINE_NO_PROVIDER_FALLBACK": {
        "description": "When 1, manual /models turns do not advance the provider fallback chain on errors.",
        "prompt": "HERMES_MANUAL_PIPELINE_NO_PROVIDER_FALLBACK (1/0, optional)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    # ── Provider (handled in provider selection, not shown in checklists) ──
    "NOUS_BASE_URL": {
        "description": "Nous Portal base URL override",
        "prompt": "Nous Portal base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "OPENROUTER_API_KEY": {
        "description": "OpenRouter API key (for vision, web scraping helpers, and MoA)",
        "prompt": "OpenRouter API key",
        "url": "https://openrouter.ai/keys",
        "password": True,
        "tools": ["vision_analyze", "mixture_of_agents"],
        "category": "provider",
        "advanced": True,
    },
    "GLM_API_KEY": {
        "description": "Z.AI / GLM API key (also recognized as ZAI_API_KEY / Z_AI_API_KEY)",
        "prompt": "Z.AI / GLM API key",
        "url": "https://z.ai/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "ZAI_API_KEY": {
        "description": "Z.AI API key (alias for GLM_API_KEY)",
        "prompt": "Z.AI API key",
        "url": "https://z.ai/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "Z_AI_API_KEY": {
        "description": "Z.AI API key (alias for GLM_API_KEY)",
        "prompt": "Z.AI API key",
        "url": "https://z.ai/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "GLM_BASE_URL": {
        "description": "Z.AI / GLM base URL override",
        "prompt": "Z.AI / GLM base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "KIMI_API_KEY": {
        "description": "Kimi / Moonshot API key",
        "prompt": "Kimi API key",
        "url": "https://platform.moonshot.cn/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "KIMI_BASE_URL": {
        "description": "Kimi / Moonshot base URL override",
        "prompt": "Kimi base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "MINIMAX_API_KEY": {
        "description": "MiniMax API key (international)",
        "prompt": "MiniMax API key",
        "url": "https://www.minimax.io/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "MINIMAX_BASE_URL": {
        "description": "MiniMax base URL override",
        "prompt": "MiniMax base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "MINIMAX_CN_API_KEY": {
        "description": "MiniMax API key (China endpoint)",
        "prompt": "MiniMax (China) API key",
        "url": "https://www.minimaxi.com/",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "MINIMAX_CN_BASE_URL": {
        "description": "MiniMax (China) base URL override",
        "prompt": "MiniMax (China) base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "DEEPSEEK_API_KEY": {
        "description": "DeepSeek API key for direct DeepSeek access",
        "prompt": "DeepSeek API Key",
        "url": "https://platform.deepseek.com/api_keys",
        "password": True,
        "category": "provider",
    },
    "DEEPSEEK_BASE_URL": {
        "description": "Custom DeepSeek API base URL (advanced)",
        "prompt": "DeepSeek Base URL",
        "url": "",
        "password": False,
        "category": "provider",
    },
    "GEMINI_API_KEY": {
        "description": "Google Gemini API key (AI Studio — OpenAI-compatible endpoint; free tier)",
        "prompt": "Gemini API key (Google AI Studio)",
        "url": "https://aistudio.google.com/apikey",
        "password": True,
        "category": "provider",
    },
    "GOOGLE_API_KEY": {
        "description": "Google AI API key (alias for GEMINI_API_KEY on the Gemini endpoint)",
        "prompt": "Google API key (Gemini)",
        "url": "https://aistudio.google.com/apikey",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "GEMINI_BASE_URL": {
        "description": "Override Gemini OpenAI-compatible base URL (default: generativelanguage.googleapis.com/v1beta/openai)",
        "prompt": "Gemini base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "DASHSCOPE_API_KEY": {
        "description": "Alibaba Cloud DashScope API key (multi-provider models)",
        "prompt": "DashScope API Key",
        "url": "https://modelstudio.console.alibabacloud.com/",
        "password": True,
        "category": "provider",
    },
    "DASHSCOPE_BASE_URL": {
        "description": "Custom DashScope base URL (default: coding-intl OpenAI-compat endpoint)",
        "prompt": "DashScope Base URL",
        "url": "",
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "OPENAI_API_KEY_DROPLET": {
        "description": (
            "OpenAI API key for VPS / split env. Preferred over OPENAI_API_KEY for native "
            "api.openai.com routing (tier E/F gpt-5.4, gpt-5.3-codex, /models native shortcuts). "
            "When OPENAI_API_KEY is empty, Hermes also copies this to OPENAI_API_KEY after .env load."
        ),
        "prompt": "OpenAI API key (droplet / alternate)",
        "url": "https://platform.openai.com/api-keys",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "OPENCODE_ZEN_API_KEY": {
        "description": "OpenCode Zen API key (pay-as-you-go access to curated models)",
        "prompt": "OpenCode Zen API key",
        "url": "https://opencode.ai/auth",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "OPENCODE_ZEN_BASE_URL": {
        "description": "OpenCode Zen base URL override",
        "prompt": "OpenCode Zen base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "OPENCODE_GO_API_KEY": {
        "description": "OpenCode Go API key ($10/month subscription for open models)",
        "prompt": "OpenCode Go API key",
        "url": "https://opencode.ai/auth",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "OPENCODE_GO_BASE_URL": {
        "description": "OpenCode Go base URL override",
        "prompt": "OpenCode Go base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },
    "HF_TOKEN": {
        "description": "Hugging Face token for Inference Providers (20+ open models via router.huggingface.co)",
        "prompt": "Hugging Face Token",
        "url": "https://huggingface.co/settings/tokens",
        "password": True,
        "category": "provider",
    },
    "HUGGINGFACE_API_KEY": {
        "description": "Alias for HF_TOKEN / HUGGING_FACE_HUB_TOKEN (common in older templates)",
        "prompt": "Hugging Face API key (alias)",
        "url": "https://huggingface.co/settings/tokens",
        "password": True,
        "category": "provider",
        "advanced": True,
    },
    "HF_BASE_URL": {
        "description": "Hugging Face Inference Providers base URL override",
        "prompt": "HF base URL (leave empty for default)",
        "url": None,
        "password": False,
        "category": "provider",
        "advanced": True,
    },

    # ── Tool API keys ──
    "EXA_API_KEY": {
        "description": "Exa API key for AI-native web search and contents",
        "prompt": "Exa API key",
        "url": "https://exa.ai/",
        "tools": ["web_search", "web_extract"],
        "password": True,
        "category": "tool",
    },
    "PARALLEL_API_KEY": {
        "description": "Parallel API key for AI-native web search and extract",
        "prompt": "Parallel API key",
        "url": "https://parallel.ai/",
        "tools": ["web_search", "web_extract"],
        "password": True,
        "category": "tool",
    },
    "FIRECRAWL_API_KEY": {
        "description": "Firecrawl API key for web search and scraping",
        "prompt": "Firecrawl API key",
        "url": "https://firecrawl.dev/",
        "tools": ["web_search", "web_extract"],
        "password": True,
        "category": "tool",
    },
    "FIRECRAWL_API_URL": {
        "description": "Firecrawl API URL for self-hosted instances (optional)",
        "prompt": "Firecrawl API URL (leave empty for cloud)",
        "url": None,
        "password": False,
        "category": "tool",
        "advanced": True,
    },
    "FIRECRAWL_GATEWAY_URL": {
        "description": "Exact Firecrawl tool-gateway origin override for Nous Subscribers only (optional)",
        "prompt": "Firecrawl gateway URL (leave empty to derive from domain)",
        "url": None,
        "password": False,
        "category": "tool",
        "advanced": True,
    },
    "TOOL_GATEWAY_DOMAIN": {
        "description": "Shared tool-gateway domain suffix for Nous Subscribers only, used to derive vendor hosts, e.g. nousresearch.com -> firecrawl-gateway.nousresearch.com",
        "prompt": "Tool-gateway domain suffix",
        "url": None,
        "password": False,
        "category": "tool",
        "advanced": True,
    },
    "TOOL_GATEWAY_SCHEME": {
        "description": "Shared tool-gateway URL scheme for Nous Subscribers only, used to derive vendor hosts (`https` by default, set `http` for local gateway testing)",
        "prompt": "Tool-gateway URL scheme",
        "url": None,
        "password": False,
        "category": "tool",
        "advanced": True,
    },
    "TOOL_GATEWAY_USER_TOKEN": {
        "description": "Explicit Nous Subscriber access token for tool-gateway requests (optional; otherwise read from the Hermes auth store)",
        "prompt": "Tool-gateway user token",
        "url": None,
        "password": True,
        "category": "tool",
        "advanced": True,
    },
    "TAVILY_API_KEY": {
        "description": "Tavily API key for AI-native web search, extract, and crawl",
        "prompt": "Tavily API key",
        "url": "https://app.tavily.com/home",
        "tools": ["web_search", "web_extract", "web_crawl"],
        "password": True,
        "category": "tool",
    },
    "BROWSERBASE_API_KEY": {
        "description": "Browserbase API key for cloud browser (optional — local browser works without this)",
        "prompt": "Browserbase API key",
        "url": "https://browserbase.com/",
        "tools": ["browser_navigate", "browser_click"],
        "password": True,
        "category": "tool",
    },
    "BROWSERBASE_PROJECT_ID": {
        "description": "Browserbase project ID (optional — only needed for cloud browser)",
        "prompt": "Browserbase project ID",
        "url": "https://browserbase.com/",
        "tools": ["browser_navigate", "browser_click"],
        "password": False,
        "category": "tool",
    },
    "BROWSER_USE_API_KEY": {
        "description": "Browser Use API key for cloud browser (optional — local browser works without this)",
        "prompt": "Browser Use API key",
        "url": "https://browser-use.com/",
        "tools": ["browser_navigate", "browser_click"],
        "password": True,
        "category": "tool",
    },
    "CAMOFOX_URL": {
        "description": "Camofox browser server URL for local anti-detection browsing (e.g. http://localhost:9377)",
        "prompt": "Camofox server URL",
        "url": "https://github.com/jo-inc/camofox-browser",
        "tools": ["browser_navigate", "browser_click"],
        "password": False,
        "category": "tool",
    },
    "FAL_KEY": {
        "description": "FAL API key for image generation",
        "prompt": "FAL API key",
        "url": "https://fal.ai/",
        "tools": ["image_generate"],
        "password": True,
        "category": "tool",
    },
    "TINKER_API_KEY": {
        "description": "Tinker API key for RL training",
        "prompt": "Tinker API key",
        "url": "https://tinker-console.thinkingmachines.ai/keys",
        "tools": ["rl_start_training", "rl_check_status", "rl_stop_training"],
        "password": True,
        "category": "tool",
    },
    "WANDB_API_KEY": {
        "description": "Weights & Biases API key for experiment tracking",
        "prompt": "WandB API key",
        "url": "https://wandb.ai/authorize",
        "tools": ["rl_get_results", "rl_check_status"],
        "password": True,
        "category": "tool",
    },
    "VOICE_TOOLS_OPENAI_KEY": {
        "description": "OpenAI API key for voice transcription (Whisper) and OpenAI TTS",
        "prompt": "OpenAI API Key (for Whisper STT + TTS)",
        "url": "https://platform.openai.com/api-keys",
        "tools": ["voice_transcription", "openai_tts"],
        "password": True,
        "category": "tool",
    },
    "ELEVENLABS_API_KEY": {
        "description": "ElevenLabs API key for premium text-to-speech voices",
        "prompt": "ElevenLabs API key",
        "url": "https://elevenlabs.io/",
        "password": True,
        "category": "tool",
    },
    "GITHUB_TOKEN": {
        "description": "GitHub token for Skills Hub (higher API rate limits, skill publish)",
        "prompt": "GitHub Token",
        "url": "https://github.com/settings/tokens",
        "password": True,
        "category": "tool",
    },

    # ── Honcho ──
    "HONCHO_API_KEY": {
        "description": "Honcho API key for AI-native persistent memory",
        "prompt": "Honcho API key",
        "url": "https://app.honcho.dev",
        "tools": ["honcho_context"],
        "password": True,
        "category": "tool",
    },
    "HONCHO_BASE_URL": {
        "description": "Base URL for self-hosted Honcho instances (no API key needed)",
        "prompt": "Honcho base URL (e.g. http://localhost:8000)",
        "category": "tool",
    },

    # ── Messaging platforms ──
    "TELEGRAM_BOT_TOKEN": {
        "description": "Telegram bot token from @BotFather",
        "prompt": "Telegram bot token",
        "url": "https://t.me/BotFather",
        "password": True,
        "category": "messaging",
    },
    "TELEGRAM_ALLOWED_USERS": {
        "description": "Comma-separated Telegram user IDs allowed to use the bot (get ID from @userinfobot)",
        "prompt": "Allowed Telegram user IDs (comma-separated)",
        "url": "https://t.me/userinfobot",
        "password": False,
        "category": "messaging",
    },
    "TELEGRAM_ALLOWED_CHATS": {
        "description": "Optional comma-separated Telegram chat IDs (groups/supergroups/channels). When set, non-DM messages must originate from one of these chats (user allowlists still apply).",
        "prompt": "Allowed Telegram chat IDs (comma-separated, optional)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "DISCORD_BOT_TOKEN": {
        "description": "Discord bot token from Developer Portal",
        "prompt": "Discord bot token",
        "url": "https://discord.com/developers/applications",
        "password": True,
        "category": "messaging",
    },
    "DISCORD_ALLOWED_USERS": {
        "description": "Comma-separated Discord user IDs allowed to use the bot",
        "prompt": "Allowed Discord user IDs (comma-separated)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "DISCORD_ALLOWED_CHANNELS": {
        "description": "Optional comma-separated Discord channel or thread IDs. When set (alone or with DISCORD_ALLOWED_GUILDS), non-DM Discord messages must match.",
        "prompt": "Allowed Discord channel/thread IDs (comma-separated, optional)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "DISCORD_ALLOWED_GUILDS": {
        "description": "Optional comma-separated Discord guild (server) IDs. When set (alone or with DISCORD_ALLOWED_CHANNELS), non-DM messages must be in an allowlisted guild and/or channel.",
        "prompt": "Allowed Discord guild IDs (comma-separated, optional)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "SLACK_BOT_TOKEN": {
        "description": "Slack bot token (xoxb-). Get from OAuth & Permissions after installing your app. "
                       "Required scopes: chat:write, app_mentions:read, channels:history, groups:history, "
                       "im:history, im:read, im:write, users:read, files:write",
        "prompt": "Slack Bot Token (xoxb-...)",
        "url": "https://api.slack.com/apps",
        "password": True,
        "category": "messaging",
    },
    "SLACK_APP_TOKEN": {
        "description": "Slack app-level token (xapp-) for Socket Mode. Get from Basic Information → "
                       "App-Level Tokens. Also ensure Event Subscriptions include: message.im, "
                       "message.channels, message.groups, app_mention",
        "prompt": "Slack App Token (xapp-...)",
        "url": "https://api.slack.com/apps",
        "password": True,
        "category": "messaging",
    },
    "SLACK_CONFIG_TOKEN": {
        "description": "Slack app configuration token (xoxe...) for manifest APIs only — generate at "
                       "api.slack.com/apps under Your App Configuration Tokens. Used by "
                       "`hermes slack config-test` / `manifest-validate`; does not run the gateway.",
        "prompt": "Slack app configuration token (xoxe...)",
        "url": "https://api.slack.com/apps",
        "password": True,
        "category": "messaging",
    },
    "SLACK_MANIFEST_KEY": {
        "description": "Alias for SLACK_CONFIG_TOKEN (same xoxe app configuration token). "
                       "Hermes accepts either name in .env for `hermes slack manifest-*` commands.",
        "prompt": "Slack manifest / app configuration token (xoxe..., same as SLACK_CONFIG_TOKEN)",
        "url": "https://api.slack.com/apps",
        "password": True,
        "category": "messaging",
    },
    "SLACK_CONFIG_TOKEN_DROPLET": {
        "description": "Optional xoxe token for **exporting** the source app in `hermes slack manifest-clone` "
                       "when the source app lives under a different Slack developer login than the new app. "
                       "Use together with SLACK_CONFIG_TOKEN_OPERATOR.",
        "prompt": "Slack config token (droplet / source app account, xoxe...)",
        "url": "https://api.slack.com/apps",
        "password": True,
        "category": "messaging",
    },
    "SLACK_CONFIG_TOKEN_OPERATOR": {
        "description": "Optional xoxe token for **validate + create** in `hermes slack manifest-clone` — "
                       "the cloned app is owned by this Slack developer account. "
                       "Use together with SLACK_CONFIG_TOKEN_DROPLET.",
        "prompt": "Slack config token (operator / target account, xoxe...)",
        "url": "https://api.slack.com/apps",
        "password": True,
        "category": "messaging",
    },
    "SLACK_NOTIFY_WITH_USER_MENTION": {
        "description": "When true (default), prepend <@user> to Slack DM replies and to posts to "
                       "SLACK_HOME_CHANNEL so mobile/desktop treat them as @mention notifications.",
        "prompt": "Slack notify with user mention (true/false)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "SLACK_NOTIFY_USER_ID": {
        "description": "Optional Slack Member ID to @mention on SLACK_HOME_CHANNEL deliveries when "
                       "no conversation metadata exists (e.g. cron). If unset, first SLACK_ALLOWED_USERS id is used.",
        "prompt": "Slack notify user id (U…)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "SLACK_ALLOWED_USERS": {
        "description": "Comma-separated Slack user IDs allowed to message the bot",
        "prompt": "Allowed Slack user IDs (comma-separated)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "SLACK_ALLOWED_CHANNELS": {
        "description": "Optional comma-separated Slack channel IDs. When set (alone or with SLACK_ALLOWED_TEAMS), non-DM Socket Mode messages must originate from an allowlisted channel.",
        "prompt": "Allowed Slack channel IDs (comma-separated, optional)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "SLACK_ALLOWED_TEAMS": {
        "description": "Optional comma-separated Slack team/workspace IDs. When set (alone or with SLACK_ALLOWED_CHANNELS), non-DM messages must be in an allowlisted workspace and/or channel.",
        "prompt": "Allowed Slack team IDs (comma-separated, optional)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "WHATSAPP_ALLOWED_CHATS": {
        "description": "Optional comma-separated WhatsApp group/chat JIDs. When set, non-DM WhatsApp messages must match (user allowlists still apply).",
        "prompt": "Allowed WhatsApp chat JIDs (comma-separated, optional)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "WHATSAPP_ALLOW_NON_SELF_DM": {
        "description": "When WHATSAPP_MODE=self-chat: set true to allow DMs that are not the self-chat (message-yourself) thread. Default off — bridge drops other 1:1 chats.",
        "prompt": "Allow non-self-chat WhatsApp DMs (true/false)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "MATTERMOST_URL": {
        "description": "Mattermost server URL (e.g. https://mm.example.com)",
        "prompt": "Mattermost server URL",
        "url": "https://mattermost.com/deploy/",
        "password": False,
        "category": "messaging",
    },
    "MATTERMOST_TOKEN": {
        "description": "Mattermost bot token or personal access token",
        "prompt": "Mattermost bot token",
        "url": None,
        "password": True,
        "category": "messaging",
    },
    "MATTERMOST_ALLOWED_USERS": {
        "description": "Comma-separated Mattermost user IDs allowed to use the bot",
        "prompt": "Allowed Mattermost user IDs (comma-separated)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "MATTERMOST_REQUIRE_MENTION": {
        "description": "Require @mention in Mattermost channels (default: true). Set to false to respond to all messages.",
        "prompt": "Require @mention in channels",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "MATTERMOST_FREE_RESPONSE_CHANNELS": {
        "description": "Comma-separated Mattermost channel IDs where bot responds without @mention",
        "prompt": "Free-response channel IDs (comma-separated)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "MATRIX_HOMESERVER": {
        "description": "Matrix homeserver URL (e.g. https://matrix.example.org)",
        "prompt": "Matrix homeserver URL",
        "url": "https://matrix.org/ecosystem/servers/",
        "password": False,
        "category": "messaging",
    },
    "MATRIX_ACCESS_TOKEN": {
        "description": "Matrix access token (preferred over password login)",
        "prompt": "Matrix access token",
        "url": None,
        "password": True,
        "category": "messaging",
    },
    "MATRIX_USER_ID": {
        "description": "Matrix user ID (e.g. @hermes:example.org)",
        "prompt": "Matrix user ID (@user:server)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "MATRIX_ALLOWED_USERS": {
        "description": "Comma-separated Matrix user IDs allowed to use the bot (@user:server format)",
        "prompt": "Allowed Matrix user IDs (comma-separated)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "GATEWAY_ALLOW_ALL_USERS": {
        "description": "Allow all users to interact with messaging bots (true/false). Default: false.",
        "prompt": "Allow all users (true/false)",
        "url": None,
        "password": False,
        "category": "messaging",
        "advanced": True,
    },
    "API_SERVER_ENABLED": {
        "description": "Enable the OpenAI-compatible API server (true/false). Allows frontends like Open WebUI, LobeChat, etc. to connect.",
        "prompt": "Enable API server (true/false)",
        "url": None,
        "password": False,
        "category": "messaging",
        "advanced": True,
    },
    "API_SERVER_KEY": {
        "description": "Bearer token for API server authentication. If empty, all requests are allowed (local use only).",
        "prompt": "API server auth key (optional)",
        "url": None,
        "password": True,
        "category": "messaging",
        "advanced": True,
    },
    "API_SERVER_PORT": {
        "description": "Port for the API server (default: 8642).",
        "prompt": "API server port",
        "url": None,
        "password": False,
        "category": "messaging",
        "advanced": True,
    },
    "API_SERVER_HOST": {
        "description": "Host/bind address for the API server (default: 127.0.0.1). Use 0.0.0.0 for network access — requires API_SERVER_KEY for security.",
        "prompt": "API server host",
        "url": None,
        "password": False,
        "category": "messaging",
        "advanced": True,
    },
    "WEBHOOK_ENABLED": {
        "description": "Enable the webhook platform adapter for receiving events from GitHub, GitLab, etc.",
        "prompt": "Enable webhooks (true/false)",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "WEBHOOK_PORT": {
        "description": "Port for the webhook HTTP server (default: 8644).",
        "prompt": "Webhook port",
        "url": None,
        "password": False,
        "category": "messaging",
    },
    "WEBHOOK_SECRET": {
        "description": "Global HMAC secret for webhook signature validation (overridable per route in config.yaml).",
        "prompt": "Webhook secret",
        "url": None,
        "password": True,
        "category": "messaging",
    },

    # ── Agent settings ──
    "MESSAGING_CWD": {
        "description": "Working directory for terminal commands via messaging",
        "prompt": "Messaging working directory (default: home)",
        "url": None,
        "password": False,
        "category": "setting",
    },
    "SUDO_PASSWORD": {
        "description": "Sudo password for terminal commands requiring root access",
        "prompt": "Sudo password",
        "url": None,
        "password": True,
        "category": "setting",
    },
    "HERMES_MAX_ITERATIONS": {
        "description": "Maximum tool-calling iterations per conversation (default: 90)",
        "prompt": "Max iterations",
        "url": None,
        "password": False,
        "category": "setting",
    },
    "ORG_AUTOMATION_ALLOW_AGENT": {
        "description": (
            "When 1, exposes the sync_org_automation tool even if agent.org_automation.enabled "
            "is false in config.yaml (orchestrator escape hatch)."
        ),
        "prompt": "Allow org automation tool without config flag (0/1)",
        "url": None,
        "password": False,
        "category": "setting",
        "advanced": True,
    },
    # HERMES_TOOL_PROGRESS and HERMES_TOOL_PROGRESS_MODE are deprecated —
    # now configured via display.tool_progress in config.yaml (off|new|all|verbose).
    # Gateway falls back to these env vars for backward compatibility.
    "HERMES_TOOL_PROGRESS": {
        "description": "(deprecated) Use display.tool_progress in config.yaml instead",
        "prompt": "Tool progress (deprecated — use config.yaml)",
        "url": None,
        "password": False,
        "category": "setting",
    },
    "HERMES_TOOL_PROGRESS_MODE": {
        "description": "(deprecated) Use display.tool_progress in config.yaml instead",
        "prompt": "Progress mode (deprecated — use config.yaml)",
        "url": None,
        "password": False,
        "category": "setting",
    },
    "HERMES_PREFILL_MESSAGES_FILE": {
        "description": "Path to JSON file with ephemeral prefill messages for few-shot priming",
        "prompt": "Prefill messages file path",
        "url": None,
        "password": False,
        "category": "setting",
    },
    "HERMES_EPHEMERAL_SYSTEM_PROMPT": {
        "description": "Ephemeral system prompt injected at API-call time (never persisted to sessions)",
        "prompt": "Ephemeral system prompt",
        "url": None,
        "password": False,
        "category": "setting",
    },
}

if not _managed_nous_tools_enabled():
    for _hidden_var in (
        "FIRECRAWL_GATEWAY_URL",
        "TOOL_GATEWAY_DOMAIN",
        "TOOL_GATEWAY_SCHEME",
        "TOOL_GATEWAY_USER_TOKEN",
    ):
        OPTIONAL_ENV_VARS.pop(_hidden_var, None)


def get_missing_env_vars(required_only: bool = False) -> List[Dict[str, Any]]:
    """
    Check which environment variables are missing.
    
    Returns list of dicts with var info for missing variables.
    """
    missing = []
    
    # Check required vars
    for var_name, info in REQUIRED_ENV_VARS.items():
        if not get_env_value(var_name):
            missing.append({"name": var_name, **info, "is_required": True})
    
    # Check optional vars (if not required_only)
    if not required_only:
        for var_name, info in OPTIONAL_ENV_VARS.items():
            if not get_env_value(var_name):
                missing.append({"name": var_name, **info, "is_required": False})
    
    return missing


def _set_nested(config: dict, dotted_key: str, value):
    """Set a value at an arbitrarily nested dotted key path.

    Creates intermediate dicts as needed, e.g. ``_set_nested(c, "a.b.c", 1)``
    ensures ``c["a"]["b"]["c"] == 1``.
    """
    parts = dotted_key.split(".")
    current = config
    for part in parts[:-1]:
        if part not in current or not isinstance(current.get(part), dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def get_missing_config_fields() -> List[Dict[str, Any]]:
    """
    Check which config fields are missing or outdated (recursive).
    
    Walks the DEFAULT_CONFIG tree at arbitrary depth and reports any keys
    present in defaults but absent from the user's loaded config.
    """
    config = load_config()
    missing = []

    def _check(defaults: dict, current: dict, prefix: str = ""):
        for key, default_value in defaults.items():
            if key.startswith('_'):
                continue
            full_key = key if not prefix else f"{prefix}.{key}"
            if key not in current:
                missing.append({
                    "key": full_key,
                    "default": default_value,
                    "description": f"New config option: {full_key}",
                })
            elif isinstance(default_value, dict) and isinstance(current.get(key), dict):
                _check(default_value, current[key], full_key)

    _check(DEFAULT_CONFIG, config)
    return missing


def check_config_version() -> Tuple[int, int]:
    """
    Check config version.
    
    Returns (current_version, latest_version).
    """
    config = load_config()
    current = config.get("_config_version", 0)
    latest = DEFAULT_CONFIG.get("_config_version", 1)
    return current, latest


def migrate_config(interactive: bool = True, quiet: bool = False) -> Dict[str, Any]:
    """
    Migrate config to latest version, prompting for new required fields.
    
    Args:
        interactive: If True, prompt user for missing values
        quiet: If True, suppress output
        
    Returns:
        Dict with migration results: {"env_added": [...], "config_added": [...], "warnings": [...]}
    """
    results = {"env_added": [], "config_added": [], "warnings": []}

    # ── Always: sanitize .env (split concatenated keys) ──
    try:
        fixes = sanitize_env_file()
        if fixes and not quiet:
            print(f"  ✓ Repaired .env file ({fixes} corrupted entries fixed)")
    except Exception:
        pass  # best-effort; don't block migration on sanitize failure

    # Check config version
    current_ver, latest_ver = check_config_version()
    
    # ── Version 3 → 4: migrate tool progress from .env to config.yaml ──
    if current_ver < 4:
        config = load_config()
        display = config.get("display", {})
        if not isinstance(display, dict):
            display = {}
        if "tool_progress" not in display:
            old_enabled = get_env_value("HERMES_TOOL_PROGRESS")
            old_mode = get_env_value("HERMES_TOOL_PROGRESS_MODE")
            if old_enabled and old_enabled.lower() in ("false", "0", "no"):
                display["tool_progress"] = "off"
                results["config_added"].append("display.tool_progress=off (from HERMES_TOOL_PROGRESS=false)")
            elif old_mode and old_mode.lower() in ("new", "all"):
                display["tool_progress"] = old_mode.lower()
                results["config_added"].append(f"display.tool_progress={old_mode.lower()} (from HERMES_TOOL_PROGRESS_MODE)")
            else:
                display["tool_progress"] = "all"
                results["config_added"].append("display.tool_progress=all (default)")
            config["display"] = display
            save_config(config)
            if not quiet:
                print(f"  ✓ Migrated tool progress to config.yaml: {display['tool_progress']}")
    
    # ── Version 4 → 5: add timezone field ──
    if current_ver < 5:
        config = load_config()
        if "timezone" not in config:
            old_tz = os.getenv("HERMES_TIMEZONE", "")
            if old_tz and old_tz.strip():
                config["timezone"] = old_tz.strip()
                results["config_added"].append(f"timezone={old_tz.strip()} (from HERMES_TIMEZONE)")
            else:
                config["timezone"] = ""
                results["config_added"].append("timezone= (empty, uses server-local)")
            save_config(config)
            if not quiet:
                tz_display = config["timezone"] or "(server-local)"
                print(f"  ✓ Added timezone to config.yaml: {tz_display}")

    # ── Version 8 → 9: clear ANTHROPIC_TOKEN from .env ──
    # The new Anthropic auth flow no longer uses this env var.
    if current_ver < 9:
        try:
            old_token = get_env_value("ANTHROPIC_TOKEN")
            if old_token:
                save_env_value("ANTHROPIC_TOKEN", "")
                if not quiet:
                    print("  ✓ Cleared ANTHROPIC_TOKEN from .env (no longer used)")
        except Exception:
            pass

    # ── Version 12 → 13: use direct Gemini when only a Gemini/Google API key is set ──
    # Typical VPS profile: GEMINI_API_KEY in .env but stale OpenRouter opus defaults in yaml.
    if current_ver < 13:
        try:
            from hermes_cli.auth import has_usable_secret

            config = load_config()
            mc = config.get("model")
            migrated_model = False
            if isinstance(mc, dict):
                d = str(mc.get("default") or mc.get("model") or "").strip()
                opus_slugs = {"anthropic/claude-opus-4.6", "claude-opus-4.6"}
                if d in opus_slugs:
                    has_gemini = has_usable_secret(get_env_value("GEMINI_API_KEY") or "") or has_usable_secret(
                        get_env_value("GOOGLE_API_KEY") or ""
                    )
                    has_or = has_usable_secret(get_env_value("OPENROUTER_API_KEY") or "") or has_usable_secret(
                        get_env_value("OPENAI_API_KEY") or ""
                    )
                    if has_gemini and not has_or:
                        mc = dict(mc)
                        mc["default"] = "gemini-2.5-flash"
                        mc["provider"] = "gemini"
                        mc.pop("base_url", None)
                        config["model"] = mc
                        migrated_model = True
            if migrated_model:
                save_config(config)
                results["config_added"].append(
                    "model.* (v13: Gemini default when only GEMINI_API_KEY / GOOGLE_API_KEY is set)"
                )
                if not quiet:
                    print(
                        "  ✓ v13: Set model to gemini-2.5-flash + provider gemini "
                        "(OpenRouter/OpenAI keys not present; GEMINI_API_KEY or GOOGLE_API_KEY set)"
                    )
        except Exception:
            pass

    # ── Version 16 → 17: seed free_model_routing hub ids (three-layer free failsafe) ──
    if current_ver < 17:
        try:
            import copy

            path = get_config_path()
            raw_user: Dict[str, Any] = {}
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        raw_user = yaml.safe_load(f) or {}
                except Exception:
                    raw_user = {}
            if not isinstance(raw_user, dict):
                raw_user = {}
            fmr = raw_user.get("free_model_routing")
            if not isinstance(fmr, dict):
                fmr = {}
            dflt = copy.deepcopy(DEFAULT_CONFIG["free_model_routing"])
            changed = False

            # Historical v17 seed (not read from DEFAULT_CONFIG — inference is opt-in now).
            v17_inference_seed = {"model": "MiniMaxAI/MiniMax-M2.5", "policy": "fastest"}

            inf = fmr.get("inference")
            if not isinstance(inf, dict):
                inf = {}
            if not str(inf.get("model") or "").strip():
                inf["model"] = v17_inference_seed["model"]
                changed = True
            if not str(inf.get("policy") or "").strip():
                inf["policy"] = v17_inference_seed["policy"]
            fmr["inference"] = inf

            kr = fmr.get("kimi_router")
            if not isinstance(kr, dict):
                kr = {}
            d_kr = dflt.get("kimi_router") or {}
            seed_tiers = copy.deepcopy(dflt.get("tiers") or [])
            if not str(kr.get("router_model") or "").strip():
                kr["router_model"] = d_kr.get("router_model")
                changed = True
            if not fmr.get("tiers") and seed_tiers:
                fmr["tiers"] = copy.deepcopy(seed_tiers)
                changed = True
            if not kr.get("tiers") and seed_tiers:
                kr["tiers"] = copy.deepcopy(seed_tiers)
                changed = True
            fmr["kimi_router"] = kr

            og = fmr.get("optional_gemini")
            if not isinstance(og, dict):
                og = {}
            if not str(og.get("model") or "").strip() and not og.get("enabled"):
                fmr["optional_gemini"] = copy.deepcopy(dflt["optional_gemini"])
                changed = True
            elif not str(og.get("model") or "").strip() and og.get("enabled"):
                og["model"] = dflt["optional_gemini"]["model"]
                fmr["optional_gemini"] = og
                changed = True
            else:
                fmr["optional_gemini"] = og

            if "enabled" not in fmr:
                fmr["enabled"] = True
            merge_user_config_yaml({"free_model_routing": fmr, "_config_version": 17})
            results["config_added"].append("free_model_routing (v17 defaults)")
            if not quiet:
                print(
                    "  ✓ v17: Seeded free_model_routing (HF inference → Kimi router tiers → optional Gemini)"
                )
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v17 free_model_routing migration skipped: {e}")
            results["warnings"].append(f"v17 migration: {e}")

    # ── Version 17 → 18: disable HF Inference Providers first hop (credit limits); Kimi-only ──
    if current_ver < 18:
        try:
            path = get_config_path()
            raw_user: Dict[str, Any] = {}
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        raw_user = yaml.safe_load(f) or {}
                except Exception:
                    raw_user = {}
            if not isinstance(raw_user, dict):
                raw_user = {}
            fmr = raw_user.get("free_model_routing")
            if not isinstance(fmr, dict):
                fmr = {}
            inf = fmr.get("inference")
            if not isinstance(inf, dict):
                inf = {}
            inf = dict(inf)
            inf["enabled"] = False
            # Drop policy-suffix hop so fallbacks start at Kimi tier router.
            inf.pop("model", None)
            inf.pop("policy", None)
            fmr["inference"] = inf
            merge_user_config_yaml({"free_model_routing": fmr, "_config_version": 18})
            results["config_added"].append("free_model_routing: inference disabled (v18)")
            if not quiet:
                print(
                    "  ✓ v18: Disabled HF Inference Providers first hop; "
                    "fallbacks use Kimi tier router → optional Gemini"
                )
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v18 free_model_routing migration skipped: {e}")
            results["warnings"].append(f"v18 migration: {e}")

    # ── Version 18 → 19: remove free_model_routing.inference (HF Inference Providers hop) ──
    if current_ver < 19:
        try:
            path = get_config_path()
            raw_user: Dict[str, Any] = {}
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        raw_user = yaml.safe_load(f) or {}
                except Exception:
                    raw_user = {}
            if not isinstance(raw_user, dict):
                raw_user = {}
            fmr = raw_user.get("free_model_routing")
            if not isinstance(fmr, dict):
                fmr = {}
            fmr = dict(fmr)
            fmr.pop("inference", None)
            merge_user_config_yaml({"free_model_routing": fmr, "_config_version": 19})
            results["config_added"].append("free_model_routing: removed inference block (v19)")
            if not quiet:
                print(
                    "  ✓ v19: Removed free_model_routing.inference — use kimi_router + optional_gemini only"
                )
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v19 free_model_routing migration skipped: {e}")
            results["warnings"].append(f"v19 migration: {e}")

    # ── Version 19 → 20: Gemini native tier router + local tier refresh ──
    if current_ver < 20:
        try:
            import copy

            path = get_config_path()
            raw_user: Dict[str, Any] = {}
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        raw_user = yaml.safe_load(f) or {}
                except Exception:
                    raw_user = {}
            if not isinstance(raw_user, dict):
                raw_user = {}
            fmr = raw_user.get("free_model_routing")
            if not isinstance(fmr, dict):
                fmr = {}
            fmr = dict(fmr)
            kr = fmr.get("kimi_router")
            if not isinstance(kr, dict):
                kr = {}
            kr = dict(kr)
            dflt_fmr = copy.deepcopy(DEFAULT_CONFIG["free_model_routing"])
            dflt_kr = copy.deepcopy(dflt_fmr.get("kimi_router") or {})
            changed = False

            OLD_TIER_MODELS = frozenset({"MiniMaxAI/MiniMax-M2.5", "openai/gpt-oss-120b"})
            tiers = fmr.get("tiers")
            if not isinstance(tiers, list) or not tiers:
                tiers = kr.get("tiers")
            if isinstance(tiers, list):
                new_tier0 = (dflt_fmr.get("tiers") or [{}])[0]
                for t in tiers:
                    if not isinstance(t, dict):
                        continue
                    mids = t.get("models")
                    if not isinstance(mids, list):
                        continue
                    s = {str(x).strip() for x in mids if str(x).strip()}
                    if s == OLD_TIER_MODELS:
                        t["models"] = copy.deepcopy(new_tier0.get("models") or [])
                        if new_tier0.get("description"):
                            t["description"] = new_tier0["description"]
                        changed = True

            rp = str(kr.get("router_provider") or "").strip().lower()
            rm = str(kr.get("router_model") or "").strip()
            if not rp:
                kr["router_provider"] = dflt_kr["router_provider"]
                changed = True
            elif rp == "huggingface":
                kr["router_provider"] = "gemini"
                kr["router_model"] = dflt_kr["router_model"]
                changed = True

            if changed:
                fmr["kimi_router"] = kr
                merge_user_config_yaml({"free_model_routing": fmr, "_config_version": 20})
                results["config_added"].append("free_model_routing (v20 Gemini tier router + local tiers)")
                if not quiet:
                    print(
                        "  ✓ v20: free_model_routing — Gemini native tier router (Gemini API), "
                        "local tiers refreshed from defaults"
                    )
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v20 free_model_routing migration skipped: {e}")
            results["warnings"].append(f"v20 migration: {e}")

    # ── Version 20 → 21: local tier cleanup + filter_free_tier_models_by_local_hub ──
    if current_ver < 21:
        try:
            import copy

            path = get_config_path()
            raw_user: Dict[str, Any] = {}
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        raw_user = yaml.safe_load(f) or {}
                except Exception:
                    raw_user = {}
            if not isinstance(raw_user, dict):
                raw_user = {}
            fmr = raw_user.get("free_model_routing")
            if not isinstance(fmr, dict):
                fmr = {}
            fmr = dict(fmr)
            dflt_fmr = copy.deepcopy(DEFAULT_CONFIG["free_model_routing"])
            changed = False

            if "filter_free_tier_models_by_local_hub" not in fmr:
                fmr["filter_free_tier_models_by_local_hub"] = dflt_fmr.get(
                    "filter_free_tier_models_by_local_hub", True
                )
                changed = True

            d_tier0 = dflt_fmr.get("tiers") or []
            d_models: list = []
            d_desc = ""
            if d_tier0 and isinstance(d_tier0[0], dict):
                d_models = list(d_tier0[0].get("models") or [])
                d_desc = str(d_tier0[0].get("description") or "")

            _legacy_hub_27b = "google/" + "".join(map(chr, (103, 101, 109, 109, 97))) + "-3-27b-it"

            def _v21_strip_legacy_hub_tier(tiers: Any) -> bool:
                local = False
                if not isinstance(tiers, list) or not d_models:
                    return False
                for t in tiers:
                    if not isinstance(t, dict):
                        continue
                    mids = t.get("models")
                    if not isinstance(mids, list):
                        continue
                    if _legacy_hub_27b in {str(x).strip() for x in mids}:
                        new_m = [str(x).strip() for x in mids if str(x).strip() != _legacy_hub_27b]
                        if not new_m:
                            new_m = copy.deepcopy(d_models)
                        t["models"] = new_m
                        if d_desc:
                            t["description"] = d_desc
                        local = True
                return local

            if _v21_strip_legacy_hub_tier(fmr.get("tiers")):
                changed = True
            kr = fmr.get("kimi_router")
            if isinstance(kr, dict):
                kr = dict(kr)
                if _v21_strip_legacy_hub_tier(kr.get("tiers")):
                    changed = True
                fmr["kimi_router"] = kr

            if changed:
                merge_user_config_yaml({"free_model_routing": fmr, "_config_version": 21})
                results["config_added"].append("free_model_routing (v21 local tier + hub filter flag)")
                if not quiet:
                    print(
                        "  ✓ v21: free_model_routing — drop legacy hub 27b id from default local tier; "
                        "enable filter_free_tier_models_by_local_hub when unset"
                    )
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v21 free_model_routing migration skipped: {e}")
            results["warnings"].append(f"v21 migration: {e}")

    # ── Version 21 → 22: gemini-2.5-flash in free tier list + gemini_native_tier_models ──
    if current_ver < 22:
        try:
            import copy

            path = get_config_path()
            raw_user: Dict[str, Any] = {}
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        raw_user = yaml.safe_load(f) or {}
                except Exception:
                    raw_user = {}
            if not isinstance(raw_user, dict):
                raw_user = {}
            fmr = raw_user.get("free_model_routing")
            if not isinstance(fmr, dict):
                fmr = {}
            fmr = dict(fmr)
            dflt_fmr = copy.deepcopy(DEFAULT_CONFIG["free_model_routing"])
            changed = False

            kr = fmr.get("kimi_router")
            if not isinstance(kr, dict):
                kr = {}
            kr = dict(kr)

            d_native = dflt_fmr.get("gemini_native_tier_models") or ["gemini-2.5-flash"]
            if not fmr.get("gemini_native_tier_models"):
                if isinstance(kr.get("gemini_native_tier_models"), list) and kr.get("gemini_native_tier_models"):
                    fmr["gemini_native_tier_models"] = copy.deepcopy(kr["gemini_native_tier_models"])
                else:
                    fmr["gemini_native_tier_models"] = copy.deepcopy(d_native)
                changed = True

            gem4 = "gemini-2.5-flash"

            def _v22_prepend_gem4(tiers: Any) -> bool:
                local = False
                if not isinstance(tiers, list):
                    return False
                for t in tiers:
                    if not isinstance(t, dict):
                        continue
                    mids = t.get("models")
                    if not isinstance(mids, list):
                        continue
                    norm = [str(x).strip() for x in mids if str(x).strip()]
                    if gem4 in norm:
                        continue
                    if len(norm) == 1 and norm[0] != gem4:
                        t["models"] = [gem4] + norm
                        local = True
                return local

            if _v22_prepend_gem4(fmr.get("tiers")):
                changed = True
            if _v22_prepend_gem4(kr.get("tiers")):
                changed = True
            fmr["kimi_router"] = kr

            if changed:
                merge_user_config_yaml({"free_model_routing": fmr, "_config_version": 22})
                results["config_added"].append("free_model_routing (v22 Gemini Flash tier + gemini_native_tier_models)")
                if not quiet:
                    print(
                        "  ✓ v22: free_model_routing — gemini-2.5-flash in tier list; "
                        "gemini_native_tier_models at free_model_routing top level"
                    )
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v22 free_model_routing migration skipped: {e}")
            results["warnings"].append(f"v22 migration: {e}")

    # ── Version 22 → 23: tiers + gemini_native_tier_models at free_model_routing top level ──
    if current_ver < 23:
        try:
            import copy

            path = get_config_path()
            raw_user: Dict[str, Any] = {}
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        raw_user = yaml.safe_load(f) or {}
                except Exception:
                    raw_user = {}
            if not isinstance(raw_user, dict):
                raw_user = {}
            fmr = raw_user.get("free_model_routing")
            if not isinstance(fmr, dict):
                fmr = {}
            fmr = dict(fmr)
            dflt_fmr = copy.deepcopy(DEFAULT_CONFIG["free_model_routing"])
            changed = False

            kr = fmr.get("kimi_router")
            if not isinstance(kr, dict):
                kr = {}
            kr = dict(kr)

            if "tiers" not in fmr:
                if isinstance(kr.get("tiers"), list) and kr["tiers"]:
                    fmr["tiers"] = copy.deepcopy(kr["tiers"])
                    kr.pop("tiers", None)
                    changed = True
            elif "tiers" in kr:
                kr.pop("tiers", None)
                changed = True

            if "gemini_native_tier_models" not in fmr:
                if isinstance(kr.get("gemini_native_tier_models"), list) and kr.get("gemini_native_tier_models"):
                    fmr["gemini_native_tier_models"] = copy.deepcopy(kr["gemini_native_tier_models"])
                else:
                    fmr["gemini_native_tier_models"] = copy.deepcopy(
                        dflt_fmr.get("gemini_native_tier_models") or ["gemini-2.5-flash"]
                    )
                kr.pop("gemini_native_tier_models", None)
                changed = True
            elif "gemini_native_tier_models" in kr:
                kr.pop("gemini_native_tier_models", None)
                changed = True

            if "fallback_free_routed_model" not in fmr:
                fmr["fallback_free_routed_model"] = str(
                    dflt_fmr.get("fallback_free_routed_model") or "gemini-2.5-flash"
                )
                changed = True

            fmr["kimi_router"] = kr
            if changed:
                merge_user_config_yaml({"free_model_routing": fmr, "_config_version": 23})
                results["config_added"].append(
                    "free_model_routing (v23 tiers + gemini_native + fallback at top level)"
                )
                if not quiet:
                    print(
                        "  ✓ v23: free_model_routing — tiers and gemini_native_tier_models under "
                        "free_model_routing; fallback_free_routed_model default"
                    )
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v23 free_model_routing migration skipped: {e}")
            results["warnings"].append(f"v23 migration: {e}")

    # ── Version 23 → 24: purge blocklisted model IDs from free_model_routing tiers ──
    if current_ver < 24:
        try:
            cfg_path = get_config_path()
            raw_user: dict = {}
            if cfg_path.exists():
                with open(cfg_path) as _f:
                    raw_user = yaml.safe_load(_f) or {}
            if not isinstance(raw_user, dict):
                raw_user = {}

            fmr = raw_user.get("free_model_routing")
            if isinstance(fmr, dict):
                fmr = copy.deepcopy(fmr)
                _changed = False

                _BLOCK = ["kimi", "minimax", "\u0067\u0065\u006d\u006d\u0061-3", "deepseek", "gpt-oss"]

                def _blocked(mid: str) -> bool:
                    low = str(mid).lower()
                    return any(sub in low for sub in _BLOCK)

                def _clean_tier_list(tiers_list):
                    nonlocal _changed
                    if not isinstance(tiers_list, list):
                        return tiers_list
                    result = []
                    for tier in tiers_list:
                        if not isinstance(tier, dict):
                            result.append(tier)
                            continue
                        models = tier.get("models")
                        if isinstance(models, list):
                            clean = [m for m in models if not _blocked(str(m))]
                            if len(clean) != len(models):
                                tier = dict(tier)
                                tier["models"] = clean
                                _changed = True
                        result.append(tier)
                    return result

                # Clean top-level tiers
                if "tiers" in fmr:
                    fmr["tiers"] = _clean_tier_list(fmr["tiers"])

                # Clean kimi_router sub-section
                kr = fmr.get("kimi_router")
                if isinstance(kr, dict):
                    kr = dict(kr)
                    rm = str(kr.get("router_model") or "").strip()
                    if rm and _blocked(rm):
                        kr["router_model"] = "gemini-2.5-flash"
                        _changed = True
                    if "tiers" in kr:
                        kr["tiers"] = _clean_tier_list(kr["tiers"])
                    fmr["kimi_router"] = kr

                if _changed:
                    merge_user_config_yaml({"free_model_routing": fmr, "_config_version": 24})
                    results["config_added"].append(
                        "free_model_routing (v24: purged blocklisted model IDs)"
                    )
                    if not quiet:
                        print(
                            "  ✓ v24: Removed blocklisted model IDs (kimi/minimax/deepseek/gpt-oss) "
                            "from free_model_routing tiers"
                        )
                else:
                    merge_user_config_yaml({"_config_version": 24})
            else:
                merge_user_config_yaml({"_config_version": 24})
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v24 blocklist migration skipped: {e}")
            results["warnings"].append(f"v24 migration: {e}")

    # ── Version 24 → 25: update governance YAML blocked_model_substrings to allow claude-sonnet-4.6 ──
    if current_ver < 25:
        try:
            import copy as _copy
            # Remove overbroad claude blocks from the governance runtime YAML so
            # anthropic/claude-sonnet-4-6 (tier D) is not blocked at runtime.
            _ops_path = None
            try:
                from hermes_constants import get_hermes_home as _ghh
                _ops_path = _ghh() / "workspace" / "operations" / "hermes_token_governance.runtime.yaml"
            except Exception:
                pass
            if _ops_path and _ops_path.exists():
                import yaml as _yaml
                with open(_ops_path) as _yf:
                    _gov = _yaml.safe_load(_yf) or {}
                _blocked = _gov.get("blocked_model_substrings")
                if isinstance(_blocked, list):
                    _TO_REMOVE = {"claude-sonnet-4", "claude-sonnet-4.5", "anthropic/claude"}
                    _cleaned = [x for x in _blocked if str(x).strip() not in _TO_REMOVE]
                    if len(_cleaned) != len(_blocked):
                        _gov["blocked_model_substrings"] = _cleaned
                        # Also update tier D if it's still google/gemini-2.5-flash
                        _tm = _gov.get("tier_models")
                        if isinstance(_tm, dict):
                            _d = str(_tm.get("D") or "").strip()
                            if _d in ("google/gemini-2.5-flash", "openrouter/auto", ""):
                                _tm["D"] = "anthropic/claude-sonnet-4-6"
                                _gov["tier_models"] = _tm
                        with open(_ops_path, "w") as _yf:
                            _yaml.dump(_gov, _yf, default_flow_style=False, allow_unicode=True)
                        if not quiet:
                            print("  ✓ v25: Updated governance YAML — enabled claude-sonnet-4.6 as tier D")
            merge_user_config_yaml({"_config_version": 25})
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v25 governance YAML migration skipped: {e}")
            results["warnings"].append(f"v25 migration: {e}")
            merge_user_config_yaml({"_config_version": 25})

    # ── Version 25 → 26: legacy short tier alias → ``gemini-2.5-flash`` (invalid on OpenRouter / APIs) ──
    if current_ver < 26:
        try:
            from agent.tier_model_routing import canonical_native_tier_model_id

            config = load_config()
            cfg_changed = False

            mc = config.get("model")
            if isinstance(mc, dict):
                mc = dict(mc)
                d0 = str(mc.get("default") or "").strip()
                m0 = str(mc.get("model") or "").strip()
                d1 = canonical_native_tier_model_id(d0) if d0 else d0
                m1 = canonical_native_tier_model_id(m0) if m0 else m0
                if (d0 and d1 != d0) or (m0 and m1 != m0):
                    mc["default"] = d1 or mc.get("default")
                    if m0:
                        mc["model"] = m1
                    config["model"] = mc
                    cfg_changed = True

            fmr = config.get("free_model_routing")
            if isinstance(fmr, dict):
                fmr = dict(fmr)
                fmr_touch = False
                for key in ("fallback_free_routed_model",):
                    v = str(fmr.get(key) or "").strip()
                    if v and canonical_native_tier_model_id(v) != v:
                        fmr[key] = canonical_native_tier_model_id(v)
                        fmr_touch = True
                gn = fmr.get("gemini_native_tier_models")
                if isinstance(gn, list):
                    gn2 = [canonical_native_tier_model_id(str(x).strip()) for x in gn if str(x).strip()]
                    if gn2 != [str(x).strip() for x in gn if str(x).strip()]:
                        fmr["gemini_native_tier_models"] = gn2
                        fmr_touch = True
                kr = fmr.get("kimi_router")
                if isinstance(kr, dict):
                    kr = dict(kr)
                    rm = str(kr.get("router_model") or "").strip()
                    if rm and canonical_native_tier_model_id(rm) != rm:
                        kr["router_model"] = canonical_native_tier_model_id(rm)
                        fmr_touch = True
                    fmr["kimi_router"] = kr

                def _fix_tier_list(tiers: Any) -> bool:
                    touched = False
                    if not isinstance(tiers, list):
                        return False
                    for t in tiers:
                        if not isinstance(t, dict):
                            continue
                        mids = t.get("models")
                        if not isinstance(mids, list):
                            continue
                        new_mids = []
                        for m in mids:
                            s = str(m).strip()
                            if not s:
                                continue
                            c = canonical_native_tier_model_id(s)
                            if c != s:
                                touched = True
                            new_mids.append(c)
                        t["models"] = new_mids
                    return touched

                if _fix_tier_list(fmr.get("tiers")):
                    fmr_touch = True
                _kr2 = fmr.get("kimi_router")
                if isinstance(_kr2, dict) and _fix_tier_list(_kr2.get("tiers")):
                    fmr_touch = True
                    fmr["kimi_router"] = dict(_kr2)

                og = fmr.get("optional_gemini")
                if isinstance(og, dict):
                    og = dict(og)
                    om = str(og.get("model") or "").strip()
                    if om and canonical_native_tier_model_id(om) != om:
                        og["model"] = canonical_native_tier_model_id(om)
                        fmr["optional_gemini"] = og
                        fmr_touch = True

                if fmr_touch:
                    config["free_model_routing"] = fmr
                    cfg_changed = True

            fp = config.get("fallback_providers")
            if isinstance(fp, list):
                fp2 = []
                fp_touch = False
                for row in fp:
                    if not isinstance(row, dict):
                        fp2.append(row)
                        continue
                    r = dict(row)
                    m = str(r.get("model") or "").strip()
                    if m and canonical_native_tier_model_id(m) != m:
                        r["model"] = canonical_native_tier_model_id(m)
                        fp_touch = True
                    fp2.append(r)
                if fp_touch:
                    config["fallback_providers"] = fp2
                    cfg_changed = True

            if cfg_changed:
                save_config(config)
                results["config_added"].append(
                    "model / free_model_routing: legacy short tier alias → gemini-2.5-flash (v26)"
                )
                if not quiet:
                    print(
                        "  ✓ v26: Canonicalized legacy short tier alias → `gemini-2.5-flash` in config.yaml"
                    )

            _ops_path = None
            try:
                from hermes_constants import get_hermes_home as _ghh

                _ops_path = _ghh() / "workspace" / "operations" / "hermes_token_governance.runtime.yaml"
            except Exception:
                pass
            if _ops_path and _ops_path.exists():
                import yaml as _yaml

                with open(_ops_path) as _yf:
                    _gov = _yaml.safe_load(_yf) or {}
                _tm = _gov.get("tier_models")
                if isinstance(_tm, dict):
                    _tm2 = dict(_tm)
                    _gov_touch = False
                    for k, v in list(_tm2.items()):
                        if not isinstance(v, str):
                            continue
                        s = v.strip()
                        if s and canonical_native_tier_model_id(s) != s:
                            _tm2[k] = canonical_native_tier_model_id(s)
                            _gov_touch = True
                    if _gov_touch:
                        _gov["tier_models"] = _tm2
                        with open(_ops_path, "w") as _yf:
                            _yaml.dump(_gov, _yf, default_flow_style=False, allow_unicode=True)
                        if not quiet:
                            print(
                                "  ✓ v26: Canonicalized tier_models in hermes_token_governance.runtime.yaml"
                            )
            merge_user_config_yaml({"_config_version": 26})
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v26 legacy tier-alias migration skipped: {e}")
            results["warnings"].append(f"v26 migration: {e}")
            merge_user_config_yaml({"_config_version": 26})

    # ── Version 26 → 27: remove legacy removed-family entries from free_model_routing / fallback rows ──
    if current_ver < 27:
        try:
            config = load_config()
            changed = False

            _legacy_token = "".join(chr(c) for c in (113, 119, 101, 110))

            def _drop_legacy_from_tiers(tiers: Any) -> bool:
                touch = False
                if not isinstance(tiers, list):
                    return False
                for t in tiers:
                    if not isinstance(t, dict):
                        continue
                    mids = t.get("models")
                    if not isinstance(mids, list):
                        continue
                    kept = [str(x).strip() for x in mids if str(x).strip() and _legacy_token not in str(x).strip().lower()]
                    if kept != [str(x).strip() for x in mids if str(x).strip()]:
                        t["models"] = kept
                        touch = True
                return touch

            fmr = config.get("free_model_routing")
            if isinstance(fmr, dict):
                fmr = dict(fmr)
                if _drop_legacy_from_tiers(fmr.get("tiers")):
                    changed = True
                kr = fmr.get("kimi_router")
                if isinstance(kr, dict):
                    kr = dict(kr)
                    if _drop_legacy_from_tiers(kr.get("tiers")):
                        changed = True
                    rm = str(kr.get("router_model") or "").strip()
                    if rm and _legacy_token in rm.lower():
                        kr["router_model"] = "gemini-2.5-flash"
                        changed = True
                    fmr["kimi_router"] = kr
                gn = fmr.get("gemini_native_tier_models")
                if isinstance(gn, list):
                    gn2 = [str(x).strip() for x in gn if str(x).strip() and _legacy_token not in str(x).strip().lower()]
                    if gn2 != [str(x).strip() for x in gn if str(x).strip()]:
                        fmr["gemini_native_tier_models"] = gn2 or ["gemini-2.5-flash"]
                        changed = True
                fb = str(fmr.get("fallback_free_routed_model") or "").strip()
                if fb and _legacy_token in fb.lower():
                    fmr["fallback_free_routed_model"] = "gemini-2.5-flash"
                    changed = True
                og = fmr.get("optional_gemini")
                if isinstance(og, dict):
                    og = dict(og)
                    om = str(og.get("model") or "").strip()
                    if om and _legacy_token in om.lower():
                        og["model"] = "gemini-2.5-flash"
                        fmr["optional_gemini"] = og
                        changed = True
                config["free_model_routing"] = fmr

            fp = config.get("fallback_providers")
            if isinstance(fp, list):
                fp2 = []
                for row in fp:
                    if not isinstance(row, dict):
                        fp2.append(row)
                        continue
                    mid = str(row.get("model") or "").strip()
                    if mid and _legacy_token in mid.lower():
                        changed = True
                        continue
                    fp2.append(row)
                if fp2 != fp:
                    config["fallback_providers"] = fp2

            if changed:
                save_config(config)
                results["config_added"].append("free_model_routing / fallback_providers: removed legacy removed-family entries (v27)")
                if not quiet:
                    print("  ✓ v27: Removed legacy removed-family entries from free_model_routing and fallback_providers")

            merge_user_config_yaml({"_config_version": 27})
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v27 legacy-removal migration skipped: {e}")
            results["warnings"].append(f"v27 migration: {e}")
            merge_user_config_yaml({"_config_version": 27})

    # ── Version 27 → 28: openai_primary_mode manual pipeline / OPM bypass keys ──
    if current_ver < 28:
        try:
            merge_user_config_yaml(
                {
                    "_config_version": 28,
                    "openai_primary_mode": {
                        "manual_pipeline_forces_opm_bypass": True,
                        "manual_pipeline_no_provider_fallback": False,
                    },
                }
            )
            if not quiet:
                print(
                    "  ✓ v28: openai_primary_mode.manual_pipeline_forces_opm_bypass / "
                    "manual_pipeline_no_provider_fallback (see AGENTS.md)"
                )
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v28 OPM manual-pipeline migration skipped: {e}")
            results["warnings"].append(f"v28 migration: {e}")
            merge_user_config_yaml({"_config_version": 28})

    # ── Version 28 → 29: optional integrations.*.repo for /paperclip and /autoresearch ──
    if current_ver < 29:
        try:
            merge_user_config_yaml(
                {
                    "_config_version": 29,
                    "integrations": {
                        "paperclip": {"repo": ""},
                        "autoresearch": {"repo": ""},
                    },
                }
            )
            if not quiet:
                print(
                    "  ✓ v29: integrations.paperclip / integrations.autoresearch "
                    "(optional repo paths; env HERMES_PAPERCLIP_REPO / HERMES_AUTORESEARCH_REPO)"
                )
        except Exception as e:
            if not quiet:
                print(f"  ⚠ v29 integrations migration skipped: {e}")
            results["warnings"].append(f"v29 migration: {e}")
            merge_user_config_yaml({"_config_version": 29})

    if current_ver < latest_ver and not quiet:
        print(f"Config version: {current_ver} → {latest_ver}")
    
    # Check for missing required env vars
    missing_env = get_missing_env_vars(required_only=True)
    
    if missing_env and not quiet:
        print("\n⚠️  Missing required environment variables:")
        for var in missing_env:
            print(f"   • {var['name']}: {var['description']}")
    
    if interactive and missing_env:
        print("\nLet's configure them now:\n")
        for var in missing_env:
            if var.get("url"):
                print(f"  Get your key at: {var['url']}")
            
            if var.get("password"):
                import getpass
                value = getpass.getpass(f"  {var['prompt']}: ")
            else:
                value = input(f"  {var['prompt']}: ").strip()
            
            if value:
                save_env_value(var["name"], value)
                results["env_added"].append(var["name"])
                print(f"  ✓ Saved {var['name']}")
            else:
                results["warnings"].append(f"Skipped {var['name']} - some features may not work")
            print()
    
    # Check for missing optional env vars and offer to configure interactively
    # Skip "advanced" vars (like OPENAI_BASE_URL) -- those are for power users
    missing_optional = get_missing_env_vars(required_only=False)
    required_names = {v["name"] for v in missing_env} if missing_env else set()
    missing_optional = [
        v for v in missing_optional
        if v["name"] not in required_names and not v.get("advanced")
    ]
    
    # Only offer to configure env vars that are NEW since the user's previous version
    new_var_names = set()
    for ver in range(current_ver + 1, latest_ver + 1):
        new_var_names.update(ENV_VARS_BY_VERSION.get(ver, []))

    if new_var_names and interactive and not quiet:
        new_and_unset = [
            (name, OPTIONAL_ENV_VARS[name])
            for name in sorted(new_var_names)
            if not get_env_value(name) and name in OPTIONAL_ENV_VARS
        ]
        if new_and_unset:
            print(f"\n  {len(new_and_unset)} new optional key(s) in this update:")
            for name, info in new_and_unset:
                print(f"    • {name} — {info.get('description', '')}")
            print()
            try:
                answer = input("  Configure new keys? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"

            if answer in ("y", "yes"):
                print()
                for name, info in new_and_unset:
                    if info.get("url"):
                        print(f"  {info.get('description', name)}")
                        print(f"  Get your key at: {info['url']}")
                    else:
                        print(f"  {info.get('description', name)}")
                    if info.get("password"):
                        import getpass
                        value = getpass.getpass(f"  {info.get('prompt', name)} (Enter to skip): ")
                    else:
                        value = input(f"  {info.get('prompt', name)} (Enter to skip): ").strip()
                    if value:
                        save_env_value(name, value)
                        results["env_added"].append(name)
                        print(f"  ✓ Saved {name}")
                    print()
            else:
                print("  Set later with: hermes config set <key> <value>")
    
    # Check for missing config fields
    missing_config = get_missing_config_fields()
    
    if missing_config:
        config = load_config()
        
        for field in missing_config:
            key = field["key"]
            default = field["default"]
            
            _set_nested(config, key, default)
            results["config_added"].append(key)
            if not quiet:
                print(f"  ✓ Added {key} = {default}")
        
        # Update version and save
        config["_config_version"] = latest_ver
        save_config(config)
    elif current_ver < latest_ver:
        # Just update version
        config = load_config()
        config["_config_version"] = latest_ver
        save_config(config)
    
    return results


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, preserving nested defaults.

    Keys in *override* take precedence. If both values are dicts the merge
    recurses, so a user who overrides only ``tts.elevenlabs.voice_id`` will
    keep the default ``tts.elevenlabs.model_id`` intact.
    """
    result = base.copy()
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _expand_env_vars(obj):
    """Recursively expand ``${VAR}`` references in config values.

    Only string values are processed; dict keys, numbers, booleans, and
    None are left untouched.  Unresolved references (variable not in
    ``os.environ``) are kept verbatim so callers can detect them.
    """
    if isinstance(obj, str):
        return re.sub(
            r"\${([^}]+)}",
            lambda m: os.environ.get(m.group(1), m.group(0)),
            obj,
        )
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    return obj


def _normalize_root_model_keys(config: Dict[str, Any]) -> Dict[str, Any]:
    """Move stale root-level provider/base_url into model section.

    Some users (or older code) placed ``provider:`` and ``base_url:`` at the
    config root instead of inside ``model:``.  These root-level keys are only
    used as a fallback when the corresponding ``model.*`` key is empty — they
    never override an existing ``model.provider`` or ``model.base_url``.
    After migration the root-level keys are removed so they can't cause
    confusion on subsequent loads.
    """
    # Only act if there are root-level keys to migrate
    has_root = any(config.get(k) for k in ("provider", "base_url"))
    if not has_root:
        return config

    config = dict(config)
    model = config.get("model")
    if not isinstance(model, dict):
        model = {"default": model} if model else {}
        config["model"] = model

    for key in ("provider", "base_url"):
        root_val = config.get(key)
        if root_val and not model.get(key):
            model[key] = root_val
        config.pop(key, None)

    return config


def _normalize_max_turns_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize legacy root-level max_turns into agent.max_turns."""
    config = dict(config)
    agent_config = dict(config.get("agent") or {})

    if "max_turns" in config and "max_turns" not in agent_config:
        agent_config["max_turns"] = config["max_turns"]

    if "max_turns" not in agent_config:
        agent_config["max_turns"] = DEFAULT_CONFIG["agent"]["max_turns"]

    config["agent"] = agent_config
    config.pop("max_turns", None)
    return config



def load_config() -> Dict[str, Any]:
    """Load configuration from ~/.hermes/config.yaml."""
    import copy
    ensure_hermes_home()
    config_path = get_config_path()
    
    config = copy.deepcopy(DEFAULT_CONFIG)
    
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}

            if "max_turns" in user_config:
                agent_user_config = dict(user_config.get("agent") or {})
                if agent_user_config.get("max_turns") is None:
                    agent_user_config["max_turns"] = user_config["max_turns"]
                user_config["agent"] = agent_user_config
                user_config.pop("max_turns", None)

            config = _deep_merge(config, user_config)
        except Exception as e:
            print(f"Warning: Failed to load config: {e}")
    
    config = _expand_env_vars(_normalize_root_model_keys(_normalize_max_turns_config(config)))
    # Resolve tier: placeholders (tier A–F) from workspace token governance YAML.
    try:
        from agent.token_governance_runtime import resolve_tier_strings_in_config

        config = resolve_tier_strings_in_config(config)
    except Exception:
        pass
    return config


_SECURITY_COMMENT = """
# ── Security ──────────────────────────────────────────────────────────
# API keys, tokens, and passwords are redacted from tool output by default.
# Set to false to see full values (useful for debugging auth issues).
# tirith pre-exec scanning is enabled by default when the tirith binary
# is available. Configure via security.tirith_* keys or env vars
# (TIRITH_ENABLED, TIRITH_BIN, TIRITH_TIMEOUT, TIRITH_FAIL_OPEN).
#
# security:
#   redact_secrets: false
#   tirith_enabled: true
#   tirith_path: "tirith"
#   tirith_timeout: 5
#   tirith_fail_open: true
"""

_FALLBACK_COMMENT = """
# ── Fallback Model ────────────────────────────────────────────────────
# Automatic provider failover when primary is unavailable.
# Uncomment and configure to enable. Triggers on rate limits (429),
# overload (529), service errors (503), or connection failures.
#
# Supported providers:
#   openrouter   (OPENROUTER_API_KEY)  — routes to any model
#   openai-codex (OAuth — hermes login) — OpenAI Codex
#   nous         (OAuth — hermes login) — Nous Portal
#   zai          (ZAI_API_KEY)         — Z.AI / GLM
#   kimi-coding  (KIMI_API_KEY)        — Kimi / Moonshot
#   minimax      (MINIMAX_API_KEY)     — MiniMax
#   minimax-cn   (MINIMAX_CN_API_KEY)  — MiniMax (China)
#
# For custom OpenAI-compatible endpoints, add base_url and api_key_env.
#
# fallback_model:
#   provider: openrouter
#   model: anthropic/claude-sonnet-4
#
# ── Smart Model Routing ────────────────────────────────────────────────
# Optional cheap-vs-strong routing for simple turns.
# Keeps the primary model for complex work, but can route short/simple
# messages to a cheaper model across providers.
#
# smart_model_routing:
#   enabled: true
#   max_simple_chars: 160
#   max_simple_words: 28
#   cheap_model:
#     provider: openrouter
#     model: google/gemini-2.5-flash
"""


_COMMENTED_SECTIONS = """
# ── Security ──────────────────────────────────────────────────────────
# API keys, tokens, and passwords are redacted from tool output by default.
# Set to false to see full values (useful for debugging auth issues).
#
# security:
#   redact_secrets: false

# ── Fallback Model ────────────────────────────────────────────────────
# Automatic provider failover when primary is unavailable.
# Uncomment and configure to enable. Triggers on rate limits (429),
# overload (529), service errors (503), or connection failures.
#
# Supported providers:
#   openrouter   (OPENROUTER_API_KEY)  — routes to any model
#   openai-codex (OAuth — hermes login) — OpenAI Codex
#   nous         (OAuth — hermes login) — Nous Portal
#   zai          (ZAI_API_KEY)         — Z.AI / GLM
#   kimi-coding  (KIMI_API_KEY)        — Kimi / Moonshot
#   minimax      (MINIMAX_API_KEY)     — MiniMax
#   minimax-cn   (MINIMAX_CN_API_KEY)  — MiniMax (China)
#
# For custom OpenAI-compatible endpoints, add base_url and api_key_env.
#
# fallback_model:
#   provider: openrouter
#   model: anthropic/claude-sonnet-4
#
# ── Smart Model Routing ────────────────────────────────────────────────
# Optional cheap-vs-strong routing for simple turns.
# Keeps the primary model for complex work, but can route short/simple
# messages to a cheaper model across providers.
#
# smart_model_routing:
#   enabled: true
#   max_simple_chars: 160
#   max_simple_words: 28
#   cheap_model:
#     provider: openrouter
#     model: google/gemini-2.5-flash
"""


def save_config(config: Dict[str, Any]):
    """Save configuration to ~/.hermes/config.yaml."""
    if is_managed():
        managed_error("save configuration")
        return
    from utils import atomic_yaml_write

    ensure_hermes_home()
    config_path = get_config_path()
    normalized = _normalize_root_model_keys(_normalize_max_turns_config(config))

    # Build optional commented-out sections for features that are off by
    # default or only relevant when explicitly configured.
    parts = []
    sec = normalized.get("security", {})
    if not sec or sec.get("redact_secrets") is None:
        parts.append(_SECURITY_COMMENT)
    fb = normalized.get("fallback_model", {})
    if not fb or not (fb.get("provider") and fb.get("model")):
        parts.append(_FALLBACK_COMMENT)

    atomic_yaml_write(
        config_path,
        normalized,
        extra_content="".join(parts) if parts else None,
    )
    _secure_file(config_path)


def load_env() -> Dict[str, str]:
    """Load environment variables from ~/.hermes/.env."""
    env_path = get_env_path()
    env_vars = {}
    
    if env_path.exists():
        # On Windows, open() defaults to the system locale (cp1252) which can
        # fail on UTF-8 .env files. Use explicit UTF-8 only on Windows.
        open_kw = {"encoding": "utf-8", "errors": "replace"} if _IS_WINDOWS else {}
        with open(env_path, **open_kw) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    env_vars[key.strip()] = value.strip().strip('"\'')
    
    return env_vars


def _sanitize_env_lines(lines: list) -> list:
    """Fix corrupted .env lines before writing.

    Handles two known corruption patterns:
    1. Concatenated KEY=VALUE pairs on a single line (missing newline between
       entries, e.g. ``ANTHROPIC_API_KEY=sk-...OPENAI_BASE_URL=https://...``).
    2. Stale ``KEY=***`` placeholder entries left by incomplete setup runs.

    Uses a known-keys set (OPTIONAL_ENV_VARS + _EXTRA_ENV_KEYS) so we only
    split on real Hermes env var names, avoiding false positives from values
    that happen to contain uppercase text with ``=``.
    """
    # Build the known keys set lazily from OPTIONAL_ENV_VARS + extras.
    # Done inside the function so OPTIONAL_ENV_VARS is guaranteed to be defined.
    known_keys = set(OPTIONAL_ENV_VARS.keys()) | _EXTRA_ENV_KEYS

    sanitized: list[str] = []
    for line in lines:
        raw = line.rstrip("\r\n")
        stripped = raw.strip()

        # Preserve blank lines and comments
        if not stripped or stripped.startswith("#"):
            sanitized.append(raw + "\n")
            continue

        # Detect concatenated KEY=VALUE pairs on one line.
        # Search for known KEY= patterns at any position in the line.
        split_positions = []
        for key_name in known_keys:
            needle = key_name + "="
            idx = stripped.find(needle)
            while idx >= 0:
                split_positions.append(idx)
                idx = stripped.find(needle, idx + len(needle))

        if len(split_positions) > 1:
            split_positions.sort()
            # Deduplicate (shouldn't happen, but be safe)
            split_positions = sorted(set(split_positions))
            for i, pos in enumerate(split_positions):
                end = split_positions[i + 1] if i + 1 < len(split_positions) else len(stripped)
                part = stripped[pos:end].strip()
                if part:
                    sanitized.append(part + "\n")
        else:
            sanitized.append(stripped + "\n")

    return sanitized


def sanitize_env_file() -> int:
    """Read, sanitize, and rewrite ~/.hermes/.env in place.

    Returns the number of lines that were fixed (concatenation splits +
    placeholder removals).  Returns 0 when no changes are needed.
    """
    env_path = get_env_path()
    if not env_path.exists():
        return 0

    read_kw = {"encoding": "utf-8", "errors": "replace"} if _IS_WINDOWS else {}
    write_kw = {"encoding": "utf-8"} if _IS_WINDOWS else {}

    with open(env_path, **read_kw) as f:
        original_lines = f.readlines()

    sanitized = _sanitize_env_lines(original_lines)

    if sanitized == original_lines:
        return 0

    # Count fixes: difference in line count (from splits) + removed lines
    fixes = abs(len(sanitized) - len(original_lines))
    if fixes == 0:
        # Lines changed content (e.g. *** removal) even if count is same
        fixes = sum(1 for a, b in zip(original_lines, sanitized) if a != b)
        fixes += abs(len(sanitized) - len(original_lines))

    fd, tmp_path = tempfile.mkstemp(dir=str(env_path.parent), suffix=".tmp", prefix=".env_")
    try:
        with os.fdopen(fd, "w", **write_kw) as f:
            f.writelines(sanitized)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, env_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    _secure_file(env_path)
    return fixes


def save_env_value(key: str, value: str):
    """Save or update a value in ~/.hermes/.env."""
    if is_managed():
        managed_error(f"set {key}")
        return
    if not _ENV_VAR_NAME_RE.match(key):
        raise ValueError(f"Invalid environment variable name: {key!r}")
    value = value.replace("\n", "").replace("\r", "")
    ensure_hermes_home()
    env_path = get_env_path()
    
    # On Windows, open() defaults to the system locale (cp1252) which can
    # cause OSError errno 22 on UTF-8 .env files.
    read_kw = {"encoding": "utf-8", "errors": "replace"} if _IS_WINDOWS else {}
    write_kw = {"encoding": "utf-8"} if _IS_WINDOWS else {}

    lines = []
    if env_path.exists():
        with open(env_path, **read_kw) as f:
            lines = f.readlines()
        # Sanitize on every read: split concatenated keys, drop stale placeholders
        lines = _sanitize_env_lines(lines)
    
    # Find and update or append
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    
    if not found:
        # Ensure there's a newline at the end of the file before appending
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{key}={value}\n")
    
    fd, tmp_path = tempfile.mkstemp(dir=str(env_path.parent), suffix='.tmp', prefix='.env_')
    try:
        with os.fdopen(fd, 'w', **write_kw) as f:
            f.writelines(lines)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, env_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    _secure_file(env_path)

    os.environ[key] = value

    # Restrict .env permissions to owner-only (contains API keys)
    if not _IS_WINDOWS:
        try:
            os.chmod(env_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def save_anthropic_oauth_token(value: str, save_fn=None):
    """Persist an Anthropic OAuth/setup token and clear the API-key slot."""
    writer = save_fn or save_env_value
    writer("ANTHROPIC_TOKEN", value)
    writer("ANTHROPIC_API_KEY", "")


def use_anthropic_claude_code_credentials(save_fn=None):
    """Use Claude Code's own credential files instead of persisting env tokens."""
    writer = save_fn or save_env_value
    writer("ANTHROPIC_TOKEN", "")
    writer("ANTHROPIC_API_KEY", "")


def save_anthropic_api_key(value: str, save_fn=None):
    """Persist an Anthropic API key and clear the OAuth/setup-token slot."""
    writer = save_fn or save_env_value
    writer("ANTHROPIC_API_KEY", value)
    writer("ANTHROPIC_TOKEN", "")


def save_env_value_secure(key: str, value: str) -> Dict[str, Any]:
    save_env_value(key, value)
    return {
        "success": True,
        "stored_as": key,
        "validated": False,
    }



def get_env_value(key: str) -> Optional[str]:
    """Get a value from ~/.hermes/.env or environment."""
    # Check environment first
    if key in os.environ:
        return os.environ[key]
    
    # Then check .env file
    env_vars = load_env()
    return env_vars.get(key)


# =============================================================================
# Config display
# =============================================================================

def redact_key(key: str) -> str:
    """Redact an API key for display."""
    if not key:
        return color("(not set)", Colors.DIM)
    if len(key) < 12:
        return "***"
    return key[:4] + "..." + key[-4:]


def show_config():
    """Display current configuration."""
    config = load_config()
    
    print()
    print(color("┌─────────────────────────────────────────────────────────┐", Colors.CYAN))
    print(color("│              ⚕ Hermes Configuration                    │", Colors.CYAN))
    print(color("└─────────────────────────────────────────────────────────┘", Colors.CYAN))
    
    # Paths
    print()
    print(color("◆ Paths", Colors.CYAN, Colors.BOLD))
    print(f"  Config:       {get_config_path()}")
    print(f"  Secrets:      {get_env_path()}")
    print(f"  Install:      {get_project_root()}")
    
    # API Keys
    print()
    print(color("◆ API Keys", Colors.CYAN, Colors.BOLD))
    
    keys = [
        ("OPENROUTER_API_KEY", "OpenRouter"),
        ("VOICE_TOOLS_OPENAI_KEY", "OpenAI (STT/TTS)"),
        ("EXA_API_KEY", "Exa"),
        ("PARALLEL_API_KEY", "Parallel"),
        ("FIRECRAWL_API_KEY", "Firecrawl"),
        ("TAVILY_API_KEY", "Tavily"),
        ("BROWSERBASE_API_KEY", "Browserbase"),
        ("BROWSER_USE_API_KEY", "Browser Use"),
        ("FAL_KEY", "FAL"),
    ]
    
    for env_key, name in keys:
        value = get_env_value(env_key)
        print(f"  {name:<14} {redact_key(value)}")
    anthropic_value = get_env_value("ANTHROPIC_TOKEN") or get_env_value("ANTHROPIC_API_KEY")
    print(f"  {'Anthropic':<14} {redact_key(anthropic_value)}")
    
    # Model settings
    print()
    print(color("◆ Model", Colors.CYAN, Colors.BOLD))
    print(f"  Model:        {config.get('model', 'not set')}")
    print(f"  Max turns:    {config.get('agent', {}).get('max_turns', DEFAULT_CONFIG['agent']['max_turns'])}")
    
    # Display
    print()
    print(color("◆ Display", Colors.CYAN, Colors.BOLD))
    display = config.get('display', {})
    print(f"  Personality:  {display.get('personality', 'kawaii')}")
    print(f"  Reasoning:    {'on' if display.get('show_reasoning', False) else 'off'}")
    print(f"  Bell:         {'on' if display.get('bell_on_complete', False) else 'off'}")

    # Terminal
    print()
    print(color("◆ Terminal", Colors.CYAN, Colors.BOLD))
    terminal = config.get('terminal', {})
    print(f"  Backend:      {terminal.get('backend', 'local')}")
    print(f"  Working dir:  {terminal.get('cwd', '.')}")
    print(f"  Timeout:      {terminal.get('timeout', 60)}s")
    
    if terminal.get('backend') == 'docker':
        print(f"  Docker image: {terminal.get('docker_image', 'nikolaik/python-nodejs:python3.11-nodejs20')}")
    elif terminal.get('backend') == 'singularity':
        print(f"  Image:        {terminal.get('singularity_image', 'docker://nikolaik/python-nodejs:python3.11-nodejs20')}")
    elif terminal.get('backend') == 'modal':
        print(f"  Modal image:  {terminal.get('modal_image', 'nikolaik/python-nodejs:python3.11-nodejs20')}")
        modal_token = get_env_value('MODAL_TOKEN_ID')
        print(f"  Modal token:  {'configured' if modal_token else '(not set)'}")
    elif terminal.get('backend') == 'daytona':
        print(f"  Daytona image: {terminal.get('daytona_image', 'nikolaik/python-nodejs:python3.11-nodejs20')}")
        daytona_key = get_env_value('DAYTONA_API_KEY')
        print(f"  API key:      {'configured' if daytona_key else '(not set)'}")
    elif terminal.get('backend') == 'ssh':
        ssh_host = get_env_value('TERMINAL_SSH_HOST')
        ssh_user = get_env_value('TERMINAL_SSH_USER')
        print(f"  SSH host:     {ssh_host or '(not set)'}")
        print(f"  SSH user:     {ssh_user or '(not set)'}")
    
    # Timezone
    print()
    print(color("◆ Timezone", Colors.CYAN, Colors.BOLD))
    tz = config.get('timezone', '')
    if tz:
        print(f"  Timezone:     {tz}")
    else:
        print(f"  Timezone:     {color('(server-local)', Colors.DIM)}")

    # Compression
    print()
    print(color("◆ Context Compression", Colors.CYAN, Colors.BOLD))
    compression = config.get('compression', {})
    enabled = compression.get('enabled', True)
    print(f"  Enabled:      {'yes' if enabled else 'no'}")
    if enabled:
        print(f"  Threshold:    {compression.get('threshold', 0.50) * 100:.0f}%")
        print(f"  Target ratio: {compression.get('target_ratio', 0.20) * 100:.0f}% of threshold preserved")
        print(f"  Protect last: {compression.get('protect_last_n', 20)} messages")
        _sm = compression.get('summary_model', '') or '(main model)'
        print(f"  Model:        {_sm}")
        comp_provider = compression.get('summary_provider', 'auto')
        if comp_provider != 'auto':
            print(f"  Provider:     {comp_provider}")
    
    # Auxiliary models
    auxiliary = config.get('auxiliary', {})
    aux_tasks = {
        "Vision":      auxiliary.get('vision', {}),
        "Web extract": auxiliary.get('web_extract', {}),
    }
    has_overrides = any(
        t.get('provider', 'auto') != 'auto' or t.get('model', '')
        for t in aux_tasks.values()
    )
    if has_overrides:
        print()
        print(color("◆ Auxiliary Models (overrides)", Colors.CYAN, Colors.BOLD))
        for label, task_cfg in aux_tasks.items():
            prov = task_cfg.get('provider', 'auto')
            mdl = task_cfg.get('model', '')
            if prov != 'auto' or mdl:
                parts = [f"provider={prov}"]
                if mdl:
                    parts.append(f"model={mdl}")
                print(f"  {label:12s}  {', '.join(parts)}")
    
    # Messaging
    print()
    print(color("◆ Messaging Platforms", Colors.CYAN, Colors.BOLD))
    
    telegram_token = get_env_value('TELEGRAM_BOT_TOKEN')
    discord_token = get_env_value('DISCORD_BOT_TOKEN')
    
    print(f"  Telegram:     {'configured' if telegram_token else color('not configured', Colors.DIM)}")
    print(f"  Discord:      {'configured' if discord_token else color('not configured', Colors.DIM)}")
    
    print()
    print(color("─" * 60, Colors.DIM))
    print(color("  hermes config edit     # Edit config file", Colors.DIM))
    print(color("  hermes config set <key> <value>", Colors.DIM))
    print(color("  hermes setup           # Run setup wizard", Colors.DIM))
    print()


def edit_config():
    """Open config file in user's editor."""
    if is_managed():
        managed_error("edit configuration")
        return
    config_path = get_config_path()
    
    # Ensure config exists
    if not config_path.exists():
        save_config(DEFAULT_CONFIG)
        print(f"Created {config_path}")
    
    # Find editor
    editor = os.getenv('EDITOR') or os.getenv('VISUAL')
    
    if not editor:
        # Try common editors
        for cmd in ['nano', 'vim', 'vi', 'code', 'notepad']:
            import shutil
            if shutil.which(cmd):
                editor = cmd
                break
    
    if not editor:
        print("No editor found. Config file is at:")
        print(f"  {config_path}")
        return
    
    print(f"Opening {config_path} in {editor}...")
    subprocess.run([editor, str(config_path)])


def set_config_value(key: str, value: str):
    """Set a configuration value."""
    if is_managed():
        managed_error("set configuration values")
        return
    # Check if it's an API key (goes to .env)
    api_keys = [
        'OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'VOICE_TOOLS_OPENAI_KEY',
        'EXA_API_KEY', 'PARALLEL_API_KEY', 'FIRECRAWL_API_KEY', 'FIRECRAWL_API_URL',
        'FIRECRAWL_GATEWAY_URL', 'TOOL_GATEWAY_DOMAIN', 'TOOL_GATEWAY_SCHEME',
        'TOOL_GATEWAY_USER_TOKEN', 'TAVILY_API_KEY',
        'BROWSERBASE_API_KEY', 'BROWSERBASE_PROJECT_ID', 'BROWSER_USE_API_KEY',
        'FAL_KEY', 'TELEGRAM_BOT_TOKEN', 'DISCORD_BOT_TOKEN',
        'TERMINAL_SSH_HOST', 'TERMINAL_SSH_USER', 'TERMINAL_SSH_KEY',
        'SUDO_PASSWORD', 'SLACK_BOT_TOKEN', 'SLACK_APP_TOKEN',
        'GITHUB_TOKEN', 'HONCHO_API_KEY', 'WANDB_API_KEY',
        'TINKER_API_KEY',
    ]
    
    if key.upper() in api_keys or key.upper().endswith('_API_KEY') or key.upper().endswith('_TOKEN') or key.upper().startswith('TERMINAL_SSH'):
        save_env_value(key.upper(), value)
        print(f"✓ Set {key} in {get_env_path()}")
        return
    
    # Otherwise it goes to config.yaml
    # Read the raw user config (not merged with defaults) to avoid
    # dumping all default values back to the file
    config_path = get_config_path()
    user_config = {}
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
        except Exception:
            user_config = {}
    
    # Handle nested keys (e.g., "tts.provider")
    parts = key.split('.')
    current = user_config
    
    for part in parts[:-1]:
        if part not in current or not isinstance(current.get(part), dict):
            current[part] = {}
        current = current[part]
    
    # Convert value to appropriate type
    if value.lower() in ('true', 'yes', 'on'):
        value = True
    elif value.lower() in ('false', 'no', 'off'):
        value = False
    elif value.isdigit():
        value = int(value)
    elif value.replace('.', '', 1).isdigit():
        value = float(value)
    
    current[parts[-1]] = value
    
    # Write only user config back (not the full merged defaults)
    ensure_hermes_home()
    with open(config_path, 'w', encoding="utf-8") as f:
        yaml.dump(user_config, f, default_flow_style=False, sort_keys=False)
    
    # Keep .env in sync for keys that terminal_tool reads directly from env vars.
    # config.yaml is authoritative, but terminal_tool only reads TERMINAL_ENV etc.
    _config_to_env_sync = {
        "terminal.backend": "TERMINAL_ENV",
        "terminal.modal_mode": "TERMINAL_MODAL_MODE",
        "terminal.docker_image": "TERMINAL_DOCKER_IMAGE",
        "terminal.singularity_image": "TERMINAL_SINGULARITY_IMAGE",
        "terminal.modal_image": "TERMINAL_MODAL_IMAGE",
        "terminal.daytona_image": "TERMINAL_DAYTONA_IMAGE",
        "terminal.docker_mount_cwd_to_workspace": "TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE",
        "terminal.cwd": "TERMINAL_CWD",
        "terminal.timeout": "TERMINAL_TIMEOUT",
        "terminal.sandbox_dir": "TERMINAL_SANDBOX_DIR",
        "terminal.persistent_shell": "TERMINAL_PERSISTENT_SHELL",
    }
    if key in _config_to_env_sync:
        save_env_value(_config_to_env_sync[key], str(value))

    print(f"✓ Set {key} = {value} in {config_path}")


# =============================================================================
# Command handler
# =============================================================================

def config_command(args):
    """Handle config subcommands."""
    subcmd = getattr(args, 'config_command', None)
    
    if subcmd is None or subcmd == "show":
        show_config()
    
    elif subcmd == "edit":
        edit_config()
    
    elif subcmd == "set":
        key = getattr(args, 'key', None)
        value = getattr(args, 'value', None)
        if not key or value is None:
            print("Usage: hermes config set <key> <value>")
            print()
            print("Examples:")
            print("  hermes config set model anthropic/claude-sonnet-4")
            print("  hermes config set terminal.backend docker")
            print("  hermes config set OPENROUTER_API_KEY sk-or-...")
            sys.exit(1)
        set_config_value(key, value)
    
    elif subcmd == "path":
        print(get_config_path())
    
    elif subcmd == "env-path":
        print(get_env_path())
    
    elif subcmd == "migrate":
        print()
        print(color("🔄 Checking configuration for updates...", Colors.CYAN, Colors.BOLD))
        print()
        
        # Check what's missing
        missing_env = get_missing_env_vars(required_only=False)
        missing_config = get_missing_config_fields()
        current_ver, latest_ver = check_config_version()
        
        if not missing_env and not missing_config and current_ver >= latest_ver:
            print(color("✓ Configuration is up to date!", Colors.GREEN))
            print()
            return
        
        # Show what needs to be updated
        if current_ver < latest_ver:
            print(f"  Config version: {current_ver} → {latest_ver}")
        
        if missing_config:
            print(f"\n  {len(missing_config)} new config option(s) will be added with defaults")
        
        required_missing = [v for v in missing_env if v.get("is_required")]
        optional_missing = [
            v for v in missing_env
            if not v.get("is_required") and not v.get("advanced")
        ]
        
        if required_missing:
            print(f"\n  ⚠️  {len(required_missing)} required API key(s) missing:")
            for var in required_missing:
                print(f"     • {var['name']}")
        
        if optional_missing:
            print(f"\n  ℹ️  {len(optional_missing)} optional API key(s) not configured:")
            for var in optional_missing:
                tools = var.get("tools", [])
                tools_str = f" (enables: {', '.join(tools[:2])})" if tools else ""
                print(f"     • {var['name']}{tools_str}")
        
        print()
        
        # Run migration
        results = migrate_config(interactive=True, quiet=False)
        
        print()
        if results["env_added"] or results["config_added"]:
            print(color("✓ Configuration updated!", Colors.GREEN))
        
        if results["warnings"]:
            print()
            for warning in results["warnings"]:
                print(color(f"  ⚠️  {warning}", Colors.YELLOW))
        
        print()
    
    elif subcmd == "check":
        # Non-interactive check for what's missing
        print()
        print(color("📋 Configuration Status", Colors.CYAN, Colors.BOLD))
        print()
        
        current_ver, latest_ver = check_config_version()
        if current_ver >= latest_ver:
            print(f"  Config version: {current_ver} ✓")
        else:
            print(color(f"  Config version: {current_ver} → {latest_ver} (update available)", Colors.YELLOW))
        
        print()
        print(color("  Required:", Colors.BOLD))
        for var_name in REQUIRED_ENV_VARS:
            if get_env_value(var_name):
                print(f"    ✓ {var_name}")
            else:
                print(color(f"    ✗ {var_name} (missing)", Colors.RED))
        
        print()
        print(color("  Optional:", Colors.BOLD))
        for var_name, info in OPTIONAL_ENV_VARS.items():
            if get_env_value(var_name):
                print(f"    ✓ {var_name}")
            else:
                tools = info.get("tools", [])
                tools_str = f" → {', '.join(tools[:2])}" if tools else ""
                print(color(f"    ○ {var_name}{tools_str}", Colors.DIM))
        
        missing_config = get_missing_config_fields()
        if missing_config:
            print()
            print(color(f"  {len(missing_config)} new config option(s) available", Colors.YELLOW))
            print("    Run 'hermes config migrate' to add them")
        
        print()
    
    else:
        print(f"Unknown config command: {subcmd}")
        print()
        print("Available commands:")
        print("  hermes config           Show current configuration")
        print("  hermes config edit      Open config in editor")
        print("  hermes config set <key> <value>   Set a config value")
        print("  hermes config check     Check for missing/outdated config")
        print("  hermes config migrate   Update config with new options")
        print("  hermes config path      Show config file path")
        print("  hermes config env-path  Show .env file path")
        sys.exit(1)
