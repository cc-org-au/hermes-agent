#!/usr/bin/env python3
"""Emit agent/provider_model_routing_catalog.json (routing-oriented model catalog).

Data is sourced from official provider docs as of the embedded snapshot date.
Re-run this script after pricing/model lineup changes; verify against:
  - https://platform.openai.com/docs/pricing
  - https://docs.anthropic.com/en/docs/about-claude/models
  - https://docs.x.ai/docs/models
  - https://ai.google.dev/gemini-api/docs/pricing
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "agent" / "provider_model_routing_catalog.json"

SNAPSHOT_DATE = "2026-04-13"

# OpenAI: Standard column from platform pricing page (USD per 1M tokens).
# Tuple: (model_id, input, cached_input_or_None, output, category, reasoning_level, notes)
_OPENAI_STANDARD: list[tuple] = [
    ("gpt-5.4", 2.5, 0.25, 15.0, "flagship_chat", "high", "Default flagship; context pricing note in OpenAI docs for <272K prompt length."),
    ("gpt-5.4-mini", 0.75, 0.075, 4.5, "efficient_chat", "medium", "Lower cost GPT-5.4 family; good for drafts and tool-heavy loops."),
    ("gpt-5.4-nano", 0.2, 0.02, 1.25, "budget_chat", "low", "Cheapest GPT-5.4 tier; classification, simple transforms."),
    ("gpt-5.4-pro", 30.0, None, 180.0, "premium_flagship", "very_high", "Highest quality/latency tradeoff; use for hardest reasoning or production-critical output."),
    ("gpt-5.2", 1.75, 0.175, 14.0, "strong_chat", "high", "Strong general model; balance of capability vs 5.4 flagship."),
    ("gpt-5.2-pro", 21.0, None, 168.0, "premium_chat", "very_high", "Pro tier within 5.2 family."),
    ("gpt-5.1", 1.25, 0.125, 10.0, "strong_chat", "high", None),
    ("gpt-5", 1.25, 0.125, 10.0, "strong_chat", "high", "Baseline GPT-5; still very capable."),
    ("gpt-5-mini", 0.25, 0.025, 2.0, "efficient_chat", "medium", None),
    ("gpt-5-nano", 0.05, 0.005, 0.4, "budget_chat", "low", "Very cheap; high-volume simple tasks."),
    ("gpt-5-pro", 15.0, None, 120.0, "premium_chat", "very_high", None),
    ("gpt-4.1", 2.0, 0.5, 8.0, "legacy_chat", "medium", "Legacy; prefer GPT-5.x for new projects unless pinned."),
    ("gpt-4.1-mini", 0.4, 0.1, 1.6, "legacy_efficient", "low", None),
    ("gpt-4.1-nano", 0.1, 0.025, 0.4, "legacy_budget", "low", None),
    ("gpt-4o", 2.5, 1.25, 10.0, "multimodal_chat", "medium", "Strong multimodal; legacy vs GPT-5 vision workflows."),
    ("gpt-4o-2024-05-13", 5.0, None, 15.0, "multimodal_chat", "medium", "Dated snapshot id; pin only for reproducibility."),
    ("gpt-4o-mini", 0.15, 0.075, 0.6, "multimodal_efficient", "low", "Fast/cheap vision + text."),
    ("o1", 15.0, 7.5, 60.0, "reasoning", "reasoning_native", "Reasoning-optimized; higher latency/cost; math, planning, hard puzzles."),
    ("o1-pro", 150.0, None, 600.0, "reasoning", "reasoning_native", "Top reasoning tier; very expensive."),
    ("o3-pro", 20.0, None, 80.0, "reasoning", "reasoning_native", "o-series pro tier."),
    ("o3", 2.0, 0.5, 8.0, "reasoning", "reasoning_native", "General reasoning model; good alternative when chain-of-thought style depth needed."),
    ("o4-mini", 1.1, 0.275, 4.4, "reasoning", "reasoning_native", "Lower-cost o-family."),
    ("o3-mini", 1.1, 0.55, 4.4, "reasoning", "reasoning_native", "Compact reasoning."),
    ("o1-mini", 1.1, 0.55, 4.4, "reasoning", "reasoning_native", "Legacy mini reasoning."),
    ("gpt-4-turbo-2024-04-09", 10.0, None, 30.0, "legacy_chat", "medium", "Deprecated path; migrate."),
    ("gpt-4-0125-preview", 10.0, None, 30.0, "legacy_chat", "medium", None),
    ("gpt-4-1106-preview", 10.0, None, 30.0, "legacy_chat", "medium", None),
    ("gpt-4-1106-vision-preview", 10.0, None, 30.0, "legacy_vision", "medium", None),
    ("gpt-4-0613", 30.0, None, 60.0, "legacy_chat", "medium", "Old GPT-4; avoid unless required."),
    ("gpt-4-0314", 30.0, None, 60.0, "legacy_chat", "medium", None),
    ("gpt-4-32k", 60.0, None, 120.0, "legacy_long_context", "medium", "Historical long context."),
    ("gpt-3.5-turbo", 0.5, None, 1.5, "legacy_chat", "low", "Legacy only."),
    ("gpt-3.5-turbo-0125", 0.5, None, 1.5, "legacy_chat", "low", None),
    ("gpt-3.5-turbo-1106", 1.0, None, 2.0, "legacy_chat", "low", None),
    ("gpt-3.5-turbo-0613", 1.5, None, 2.0, "legacy_chat", "low", None),
    ("gpt-3.5-0301", 1.5, None, 2.0, "legacy_chat", "low", None),
    ("gpt-3.5-turbo-instruct", 1.5, None, 2.0, "legacy_completion", "low", "Completion-style API legacy."),
    ("gpt-3.5-turbo-16k-0613", 3.0, None, 4.0, "legacy_long_context", "low", None),
    ("davinci-002", 2.0, None, 2.0, "legacy_completion", "low", "Base model legacy."),
    ("babbage-002", 0.4, None, 0.4, "legacy_completion", "low", None),
    ("o3-deep-research", 10.0, 2.5, 40.0, "agentic_research", "reasoning_native", "Deep research agent workflow; expect multi-step tool use."),
    ("o4-mini-deep-research", 2.0, 0.5, 8.0, "agentic_research", "reasoning_native", "Lower-cost deep research."),
    ("computer-use-preview", 3.0, None, 12.0, "computer_use", "high", "GUI automation preview; specialized."),
    ("text-embedding-3-small", 0.02, None, None, "embedding", "none", "Embeddings only."),
    ("text-embedding-3-large", 0.13, None, None, "embedding", "none", None),
    ("text-embedding-ada-002", 0.1, None, None, "embedding", "none", "Legacy embedding."),
    ("omni-moderation-latest", 0.0, None, None, "moderation", "none", "Moderation; priced as free on OpenAI pricing page."),
    ("text-moderation-latest", 0.0, None, None, "moderation", "none", None),
]


def _openai_modalities(model_id: str, category: str) -> list[str]:
    if category in {"embedding", "moderation", "legacy_completion"}:
        return ["text"]
    if category in {"multimodal_chat", "multimodal_efficient", "legacy_vision"}:
        return ["text", "image"]
    if "vision" in model_id or "4o" in model_id:
        return ["text", "image"]
    if model_id.startswith("gpt-5") or category in {"flagship_chat", "efficient_chat", "budget_chat", "strong_chat", "premium_chat", "premium_flagship"}:
        return ["text", "image"]
    if category == "computer_use":
        return ["text", "image"]
    if category == "reasoning" or category == "agentic_research":
        return ["text", "image"]
    return ["text"]


def _openai_models() -> list[dict]:
    out = []
    for row in _OPENAI_STANDARD:
        mid, inp, cach, outp, cat, rlevel, note = row
        per_m: dict = {"input": inp}
        if cach is not None:
            per_m["cached_input"] = cach
        if outp is not None:
            per_m["output"] = outp
        pricing = {"usd_per_million_tokens": per_m}
        entry = {
            "id": mid,
            "category": cat,
            "reasoning_level": rlevel,
            "pricing": pricing,
            "pricing_basis": "openai_standard_2026-04-09_snapshot",
            "modalities": _openai_modalities(mid, cat),
            "best_for": [],
            "use_cases": [],
            "when_to_avoid": [],
            "notes": note or "",
        }
        if cat == "flagship_chat" or cat == "premium_flagship":
            entry["best_for"] = ["General agent tasks", "Complex coding", "Long-form analysis"]
            entry["use_cases"] = ["Primary assistant", "Architecture decisions", "Difficult debugging"]
            entry["relative_latency"] = "medium"
        elif cat == "efficient_chat":
            entry["best_for"] = ["Tool-heavy loops", "Drafting", "Subagents"]
            entry["relative_latency"] = "fast"
        elif cat == "budget_chat":
            entry["best_for"] = ["Routing", "Classification", "Summarization of simple text"]
            entry["relative_latency"] = "fastest"
        elif cat == "reasoning" or cat == "agentic_research":
            entry["best_for"] = ["Math", "Logic puzzles", "Multi-step planning", "Research synthesis"]
            entry["when_to_avoid"] = ["Trivial chat where latency/cost dominates"]
            entry["relative_latency"] = "slow"
        elif cat == "multimodal_chat" or cat == "multimodal_efficient":
            entry["modalities"] = ["text", "image"]
            entry["best_for"] = ["Vision + text", "UI screenshots", "Diagram understanding"]
            entry["relative_latency"] = "fast" if "mini" in mid else "medium"
        elif cat == "embedding":
            entry["best_for"] = ["RAG indexing", "Semantic search"]
        elif cat == "moderation":
            entry["best_for"] = ["Safety classifiers", "Policy checks"]
        elif "legacy" in cat:
            entry["when_to_avoid"] = ["New products unless compatibility requires"]
            entry["best_for"] = ["Pinned reproducible pipelines"]
        out.append(entry)
    return out


def _anthropic_models() -> list[dict]:
    return [
        {
            "id": "claude-opus-4-6",
            "aliases": ["claude-opus-4-6"],
            "category": "flagship",
            "reasoning_level": "very_high",
            "extended_thinking": True,
            "adaptive_thinking": True,
            "context_window_tokens": 1_000_000,
            "max_output_tokens": 128_000,
            "relative_latency": "moderate",
            "pricing": {
                "usd_per_million_tokens": {"input": 5.0, "output": 25.0},
                "notes": "Prompt caching, batch, and thinking-token pricing: see Anthropic pricing page.",
            },
            "modalities": ["text", "image"],
            "best_for": ["Hardest agent workloads", "Deep coding", "Long-horizon reasoning"],
            "use_cases": ["Chief orchestrator", "Security-sensitive review", "Novel problem solving"],
            "when_to_avoid": ["High-volume low-complexity traffic where Haiku suffices"],
            "knowledge_cutoff_notes": "See Anthropic models table (reliable vs training cutoff).",
        },
        {
            "id": "claude-sonnet-4-6",
            "aliases": ["claude-sonnet-4-6"],
            "category": "balanced",
            "reasoning_level": "high",
            "extended_thinking": True,
            "adaptive_thinking": True,
            "context_window_tokens": 1_000_000,
            "max_output_tokens": 64_000,
            "relative_latency": "fast",
            "pricing": {"usd_per_million_tokens": {"input": 3.0, "output": 15.0}},
            "modalities": ["text", "image"],
            "best_for": ["Production default", "Coding + tools", "Cost-performance sweet spot"],
            "use_cases": ["Daily development", "Customer-facing assistants", "Most Hermes-style agents"],
            "when_to_avoid": ["Marginal gains worth Opus cost", "Trivial classification at scale"],
        },
        {
            "id": "claude-haiku-4-5",
            "api_snapshot_id": "claude-haiku-4-5-20251001",
            "category": "fast_efficient",
            "reasoning_level": "medium",
            "extended_thinking": True,
            "adaptive_thinking": False,
            "context_window_tokens": 200_000,
            "max_output_tokens": 64_000,
            "relative_latency": "fastest",
            "pricing": {"usd_per_million_tokens": {"input": 1.0, "output": 5.0}},
            "modalities": ["text", "image"],
            "best_for": ["High throughput", "Classification", "Extraction", "First-pass triage"],
            "use_cases": ["Router models", "Cheap pre-filter", "Latency-sensitive chat"],
            "when_to_avoid": ["Frontier coding quality requirements"],
        },
        {
            "id": "claude-sonnet-4-5-20250929",
            "alias_api": "claude-sonnet-4-5",
            "category": "balanced_prior_gen",
            "reasoning_level": "high",
            "extended_thinking": True,
            "context_window_tokens": 200_000,
            "pricing": {"usd_per_million_tokens": {"input": 3.0, "output": 15.0}},
            "modalities": ["text", "image"],
            "best_for": ["Stable pinned workloads"],
            "notes": "Prior generation; migrate to 4.6 when possible.",
            "deprecation_hint": "migrate_to_claude_sonnet_4_6",
        },
        {
            "id": "claude-opus-4-5-20251101",
            "alias_api": "claude-opus-4-5",
            "category": "flagship_prior_gen",
            "reasoning_level": "very_high",
            "context_window_tokens": 200_000,
            "pricing": {"usd_per_million_tokens": {"input": 5.0, "output": 25.0}},
            "modalities": ["text", "image"],
            "notes": "Prior Opus; prefer Opus 4.6 for new work.",
        },
        {
            "id": "claude-opus-4-1-20250805",
            "alias_api": "claude-opus-4-1",
            "category": "legacy_flagship",
            "reasoning_level": "high",
            "context_window_tokens": 200_000,
            "pricing": {"usd_per_million_tokens": {"input": 15.0, "output": 75.0}},
            "modalities": ["text", "image"],
            "when_to_avoid": ["New deployments"],
        },
        {
            "id": "claude-sonnet-4-20250514",
            "alias_api": "claude-sonnet-4-0",
            "category": "legacy_balanced",
            "reasoning_level": "high",
            "context_window_tokens": 200_000,
            "pricing": {"usd_per_million_tokens": {"input": 3.0, "output": 15.0}},
            "modalities": ["text", "image"],
        },
        {
            "id": "claude-opus-4-20250514",
            "alias_api": "claude-opus-4-0",
            "category": "legacy_flagship",
            "reasoning_level": "very_high",
            "context_window_tokens": 200_000,
            "pricing": {"usd_per_million_tokens": {"input": 15.0, "output": 75.0}},
            "modalities": ["text", "image"],
        },
        {
            "id": "claude-3-haiku-20240307",
            "category": "deprecated",
            "reasoning_level": "low",
            "context_window_tokens": 200_000,
            "pricing": {"usd_per_million_tokens": {"input": 0.25, "output": 1.25}},
            "modalities": ["text", "image"],
            "notes": "Anthropic announced retirement April 19, 2026; migrate to Haiku 4.5.",
            "deprecation_hint": "retirement_2026-04-19",
        },
        {
            "id": "claude-mythos-preview",
            "category": "special_invite_only",
            "reasoning_level": "high",
            "modalities": ["text", "image"],
            "notes": "Cybersecurity defensive workflows (Project Glasswing); not self-serve.",
        },
    ]


def _xai_models() -> list[dict]:
    text_models = [
        {
            "id": "grok-4.20-0309-reasoning",
            "category": "frontier_reasoning",
            "reasoning_level": "reasoning_native",
            "context_window_tokens": 2_000_000,
            "modalities": ["text", "image"],
            "capabilities": ["functions", "structured_outputs", "reasoning"],
            "pricing": {"usd_per_million_tokens": {"input": 2.0, "cached_input": 0.2, "output": 6.0}},
            "rate_limits_hint": "10M TPM, 1800 RPM (per xAI table)",
            "best_for": ["Long-context agents", "Reasoning with tools", "X/real-time angle when using xAI search tools"],
            "use_cases": ["Research assistants", "Multi-step agents"],
            "when_to_avoid": ["Cheapest possible inference—use grok-4-1-fast-non-reasoning"],
        },
        {
            "id": "grok-4.20-0309-non-reasoning",
            "category": "frontier_chat",
            "reasoning_level": "medium",
            "context_window_tokens": 2_000_000,
            "modalities": ["text", "image"],
            "capabilities": ["functions", "structured_outputs"],
            "pricing": {"usd_per_million_tokens": {"input": 2.0, "cached_input": 0.2, "output": 6.0}},
            "best_for": ["Same tier as reasoning variant without explicit reasoning mode"],
            "notes": "Same token price as reasoning id; pick based on need for reasoning traces.",
        },
        {
            "id": "grok-4-1-fast-reasoning",
            "category": "efficient_reasoning",
            "reasoning_level": "reasoning_native",
            "context_window_tokens": 2_000_000,
            "modalities": ["text", "image"],
            "capabilities": ["functions", "structured_outputs", "reasoning"],
            "pricing": {"usd_per_million_tokens": {"input": 0.2, "cached_input": 0.05, "output": 0.5}},
            "best_for": ["High-volume reasoning", "Subagents", "Cost-sensitive Grok"],
            "relative_latency": "fast",
        },
        {
            "id": "grok-4-1-fast-non-reasoning",
            "category": "efficient_chat",
            "reasoning_level": "low",
            "context_window_tokens": 2_000_000,
            "modalities": ["text", "image"],
            "capabilities": ["functions", "structured_outputs"],
            "pricing": {"usd_per_million_tokens": {"input": 0.2, "cached_input": 0.05, "output": 0.5}},
            "best_for": ["Routers", "Cheap tool loops", "Classification"],
        },
        {
            "id": "grok-4.20-multi-agent-0309",
            "category": "multi_agent",
            "reasoning_level": "high",
            "context_window_tokens": 2_000_000,
            "modalities": ["text", "image"],
            "capabilities": ["functions", "structured_outputs", "reasoning"],
            "pricing": {"usd_per_million_tokens": {"input": 2.0, "cached_input": 0.2, "output": 6.0}},
            "best_for": ["Orchestrated multi-agent setups on xAI"],
        },
    ]
    media = [
        {
            "id": "grok-imagine-image",
            "category": "image_generation",
            "reasoning_level": "none",
            "pricing": {"usd_per_image": 0.02, "notes": "300 RPM per xAI"},
            "best_for": ["Fast image generation"],
        },
        {
            "id": "grok-imagine-image-pro",
            "category": "image_generation",
            "reasoning_level": "none",
            "pricing": {"usd_per_image": 0.07, "notes": "30 RPM per xAI"},
            "best_for": ["Higher quality image generation"],
        },
        {
            "id": "grok-imagine-video",
            "category": "video_generation",
            "reasoning_level": "none",
            "pricing": {"usd_per_second": 0.05, "notes": "60 RPM per xAI"},
            "best_for": ["Video generation workflows"],
        },
    ]
    return text_models + media


def _xai_tool_pricing() -> dict:
    return {
        "invocation_surcharge_per_1000_calls_usd": {
            "web_search": 5.0,
            "x_search": 5.0,
            "code_execution": 5.0,
            "attachment_search": 10.0,
            "collections_search": 2.5,
        },
        "notes": "Token costs still apply; image/video understanding via tools billed as tokens per xAI docs.",
    }


def _google_models() -> list[dict]:
    """Paid Standard tier excerpts (text-focused); see Google pricing for Batch/Priority/Flex."""
    return [
        {
            "id": "gemini-3.1-pro-preview",
            "aliases": ["gemini-3.1-pro-preview-customtools"],
            "category": "flagship_preview",
            "reasoning_level": "very_high",
            "context_window_notes": "Tiered pricing at 200k prompt tokens (see pricing page).",
            "pricing": {
                "usd_per_million_tokens": {
                    "input_leq_200k": 2.0,
                    "input_gt_200k": 4.0,
                    "output_leq_200k": 12.0,
                    "output_gt_200k": 18.0,
                },
                "notes": "Output includes thinking tokens; grounding to Search/Maps extra per Google table.",
            },
            "modalities": ["text", "image", "video", "audio"],
            "best_for": ["Agentic coding", "Complex multimodal reasoning", "Vibe coding workflows per Google copy"],
            "use_cases": ["Primary Gemini flagship when available on your billing tier"],
        },
        {
            "id": "gemini-3-flash-preview",
            "category": "fast_frontier_preview",
            "reasoning_level": "high",
            "pricing": {
                "usd_per_million_tokens": {
                    "input_text_image_video": 0.5,
                    "input_audio": 1.0,
                    "output": 3.0,
                }
            },
            "modalities": ["text", "image", "video", "audio"],
            "best_for": ["Speed + strong quality", "Search/grounding-oriented tasks per Google positioning"],
            "relative_latency": "fast",
        },
        {
            "id": "gemini-3.1-flash-lite-preview",
            "category": "budget_preview",
            "reasoning_level": "medium",
            "pricing": {
                "usd_per_million_tokens": {
                    "input_text_image_video": 0.25,
                    "input_audio": 0.5,
                    "output": 1.5,
                }
            },
            "modalities": ["text", "image", "video", "audio"],
            "best_for": ["High-volume agents", "Translation", "Simple data processing"],
        },
        {
            "id": "gemini-2.5-pro",
            "category": "stable_flagship",
            "reasoning_level": "high",
            "pricing": {
                "usd_per_million_tokens": {
                    "input_leq_200k": 1.25,
                    "input_gt_200k": 2.5,
                    "output_leq_200k": 10.0,
                    "output_gt_200k": 15.0,
                }
            },
            "modalities": ["text", "image", "video", "audio"],
            "best_for": ["Coding", "Complex reasoning", "Production workloads needing stable id"],
            "context_window_tokens": 1_000_000,
            "notes": "Thinking tokens included in output price.",
        },
        {
            "id": "gemini-2.5-flash",
            "category": "balanced_fast",
            "reasoning_level": "medium",
            "pricing": {
                "usd_per_million_tokens": {
                    "input_text_image_video": 0.3,
                    "input_audio": 1.0,
                    "output": 2.5,
                }
            },
            "modalities": ["text", "image", "video", "audio"],
            "best_for": ["Default fast model", "Tool use", "Hybrid reasoning with thinking budgets"],
            "context_window_tokens": 1_000_000,
        },
        {
            "id": "gemini-2.5-flash-lite",
            "category": "budget",
            "reasoning_level": "low",
            "pricing": {
                "usd_per_million_tokens": {
                    "input_text_image_video": 0.1,
                    "input_audio": 0.3,
                    "output": 0.4,
                }
            },
            "modalities": ["text", "image", "video", "audio"],
            "best_for": ["Routers", "Triage", "Massive scale"],
        },
        {
            "id": "gemini-2.5-flash-lite-preview-09-2025",
            "category": "budget_preview",
            "reasoning_level": "low",
            "pricing": {
                "usd_per_million_tokens": {
                    "input_text_image_video": 0.1,
                    "input_audio": 0.3,
                    "output": 0.4,
                }
            },
            "modalities": ["text", "image", "video", "audio"],
            "notes": "Preview variant of Flash-Lite.",
        },
        {
            "id": "gemini-3.1-flash-live-preview",
            "category": "live_audio",
            "reasoning_level": "medium",
            "modalities": ["text", "audio", "image", "video"],
            "pricing": {
                "usd_per_million_tokens": {
                    "input_text": 0.75,
                    "input_audio_alt_usd_per_minute": 0.005,
                    "input_image_video_alt_usd_per_minute": 0.002,
                    "output_text": 4.5,
                    "output_audio_alt_usd_per_minute": 0.018,
                },
                "notes": "Live API: mixed per-token and per-minute audio rates on Google pricing page.",
            },
            "best_for": ["Real-time voice agents", "Low-latency dialogue"],
            "relative_latency": "fast",
        },
        {
            "id": "gemini-3.1-flash-image-preview",
            "category": "native_image",
            "reasoning_level": "medium",
            "modalities": ["text", "image"],
            "pricing": {
                "usd_per_million_tokens": {
                    "input_text_image": 0.5,
                    "output_text_thinking": 3.0,
                    "image_output_tokens_rate_usd_per_million": 60.0,
                },
                "notes": "Image output billed as tokens (~$0.045–0.151 per image by resolution per Google).",
            },
            "best_for": ["Fast native image gen/edit", "Interactive creative tools"],
        },
        {
            "id": "gemini-3-pro-image-preview",
            "category": "native_image_pro",
            "reasoning_level": "high",
            "modalities": ["text", "image"],
            "pricing": {
                "notes": "Text/thinking aligned with Gemini 3.1 Pro rates; image output $120/1M tokens per Google.",
            },
            "best_for": ["Studio-quality layouts", "4K visuals", "Precise text-in-image"],
        },
        {
            "id": "gemini-2.5-flash-image",
            "category": "native_image",
            "reasoning_level": "medium",
            "modalities": ["text", "image"],
            "pricing": {
                "notes": "Text priced as 2.5 Flash; image output ~$0.039/image at 1K per Google table.",
            },
            "best_for": ["Quick image generation/editing"],
        },
        {
            "id": "gemini-2.5-flash-native-audio-preview-12-2025",
            "category": "live_audio",
            "reasoning_level": "medium",
            "modalities": ["text", "audio", "video"],
            "pricing": {
                "usd_per_million_tokens": {
                    "input_text": 0.5,
                    "input_audio_video": 3.0,
                    "output_text": 2.0,
                    "output_audio": 12.0,
                }
            },
            "best_for": ["Bidirectional voice/video agents", "Live API flagship (2.5 era)"],
        },
        {
            "id": "gemini-2.5-flash-preview-tts",
            "category": "tts",
            "reasoning_level": "none",
            "modalities": ["text", "audio"],
            "pricing": {
                "usd_per_million_tokens": {"input_text": 0.5, "output_audio": 10.0},
                "notes": "Batch: half price on Google pricing table.",
            },
            "best_for": ["Low-latency TTS", "Controllable speech"],
        },
        {
            "id": "gemini-2.5-pro-preview-tts",
            "category": "tts",
            "reasoning_level": "none",
            "modalities": ["text", "audio"],
            "pricing": {"usd_per_million_tokens": {"input_text": 1.0, "output_audio": 20.0}},
            "best_for": ["High-fidelity speech", "Podcasts", "Audiobooks"],
        },
        {
            "id": "imagen-4.0-generate-001",
            "category": "image_generation_external",
            "reasoning_level": "none",
            "aliases": ["imagen-4.0-ultra-generate-001", "imagen-4.0-fast-generate-001"],
            "pricing": {
                "usd_per_image": {"fast": 0.02, "standard": 0.04, "ultra": 0.06},
                "notes": "Three SKUs; see Imagen section on Google pricing page.",
            },
            "best_for": ["Text-to-image outside Gemini chat", "Marketing assets"],
        },
        {
            "id": "veo-3.1-generate-preview",
            "category": "video_generation",
            "reasoning_level": "none",
            "aliases": ["veo-3.1-fast-generate-preview", "veo-3.1-lite-generate-preview"],
            "pricing": {"notes": "Video billed per second/output unit; see Veo section on Google pricing page."},
            "best_for": ["Cinematic video with audio sync"],
        },
        {
            "id": "lyria-3-pro-preview",
            "category": "music_generation",
            "reasoning_level": "none",
            "pricing": {"notes": "See Google models/pricing pages for music SKUs."},
            "best_for": ["Full-length structured music generation"],
        },
        {
            "id": "lyria-3-clip-preview",
            "category": "music_generation",
            "reasoning_level": "none",
            "best_for": ["Short clips and loops (≤30s)"],
        },
        {
            "id": "gemini-robotics-er-1.5-preview",
            "category": "robotics_embodied",
            "reasoning_level": "high",
            "best_for": ["Embodied agents", "Physical task planning"],
            "notes": "Preview; see Gemini models documentation.",
        },
        {
            "id": "gemini-2.5-computer-use-preview-10-2025",
            "category": "computer_use",
            "reasoning_level": "high",
            "modalities": ["text", "image"],
            "best_for": ["GUI automation", "Browser control"],
            "notes": "See Gemini model page for pricing; specialized preview.",
        },
        {
            "id": "gemini-deep-research-pro-preview-12-2025",
            "category": "deep_research",
            "reasoning_level": "very_high",
            "best_for": ["Autonomous multi-source research reports"],
            "notes": "Agentic research; verify current pricing on Google page.",
        },
        {
            "id": "gemini-embedding-001",
            "category": "embedding",
            "reasoning_level": "none",
            "best_for": ["Text RAG", "Classification embeddings"],
        },
        {
            "id": "gemini-embedding-2-preview",
            "category": "embedding_multimodal",
            "reasoning_level": "none",
            "modalities": ["text", "image", "video", "audio", "pdf"],
            "best_for": ["Multimodal RAG"],
        },
        {
            "id": "gemini-2.0-flash",
            "category": "deprecated",
            "reasoning_level": "medium",
            "pricing": {
                "usd_per_million_tokens": {
                    "input_text_image_video": 0.1,
                    "input_audio": 0.7,
                    "output": 0.4,
                }
            },
            "notes": "Google deprecation: shutdown June 1, 2026; migrate to 2.5+.",
            "deprecation_hint": "shutdown_2026-06-01",
        },
        {
            "id": "gemini-2.0-flash-lite",
            "category": "deprecated",
            "reasoning_level": "low",
            "pricing": {"usd_per_million_tokens": {"input": 0.075, "output": 0.3}},
            "notes": "Shutdown June 1, 2026.",
            "deprecation_hint": "shutdown_2026-06-01",
        },
    ]


def _openrouter_hub_models() -> list[dict]:
    """OpenRouter aggregate hub slugs for routing digest and canon cross-reference.

    Pricing is indicative for paid rows (USD per 1M tokens, rough OpenRouter-style);
    :free rows use 0. Confirm on https://openrouter.ai/models before production cuts.
    """
    rows: list[tuple[str, str, str, float, float, str, str]] = [
        # OpenAI via OpenRouter (must match dynamic_routing_canon hub ladders)
        ("openai/gpt-5-nano", "hub_openai_budget", "low", 0.05, 0.4, "text", "Canon step-up / OPM failover ladder"),
        ("openai/gpt-4.1-nano", "hub_openai_budget", "low", 0.1, 0.4, "text", "Canon ladder"),
        ("openai/gpt-5-mini", "hub_openai_efficient", "medium", 0.25, 2.0, "text", "Canon ladder"),
        ("openai/gpt-4.1-mini", "hub_openai_efficient", "low", 0.4, 1.6, "text", "Canon ladder"),
        ("openai/gpt-5.4-nano", "hub_openai_budget", "low", 0.2, 1.25, "text", "Canon ladder"),
        ("openai/gpt-5.4-mini", "hub_openai_efficient", "medium", 0.75, 4.5, "text", "Canon ladder"),
        ("openai/gpt-5.2", "hub_openai_strong", "high", 1.75, 14.0, "text", "Canon ladder"),
        ("openai/gpt-5.4", "hub_openai_flagship", "high", 2.5, 15.0, "text", "Canon ladder"),
        ("openai/gpt-5.2-codex", "hub_openai_codex", "high", 1.75, 14.0, "text", "Canon codex ladder"),
        ("openai/gpt-5.3-codex", "hub_openai_codex", "high", 2.0, 16.0, "text", "Canon codex ladder"),
        ("openai/gpt-5.4-pro", "hub_openai_premium", "very_high", 30.0, 180.0, "text", "Premium tier"),
        # Anthropic via OpenRouter
        ("anthropic/claude-haiku-4.5", "hub_anthropic_efficient", "medium", 1.0, 5.0, "text", "Fast Claude"),
        ("anthropic/claude-sonnet-4.5", "hub_anthropic_balanced", "high", 3.0, 15.0, "text", "Daily driver"),
        ("anthropic/claude-sonnet-4.6", "hub_anthropic_balanced", "high", 3.0, 15.0, "text", "Balanced"),
        ("anthropic/claude-opus-4.6", "hub_anthropic_flagship", "very_high", 5.0, 25.0, "text", "Frontier"),
        # Google via OpenRouter
        ("google/gemini-2.5-flash-preview-05-20", "hub_google_fast", "medium", 0.15, 0.6, "text", "Low latency"),
        ("google/gemini-2.5-pro-preview-06-05", "hub_google_flagship", "high", 1.25, 10.0, "text", "Strong reasoning"),
        ("google/gemini-3-flash-preview", "hub_google_frontier_fast", "high", 0.5, 3.0, "text", "Preview"),
        ("google/gemini-3-pro-preview", "hub_google_frontier", "very_high", 2.0, 12.0, "text", "Preview flagship"),
        # Meta / Mistral / Qwen / DeepSeek
        ("meta-llama/llama-3.3-70b-instruct", "hub_meta_balanced", "high", 0.35, 0.4, "text", "Open weights"),
        ("mistralai/mistral-small-3.2-24b-instruct", "hub_mistral_efficient", "medium", 0.05, 0.08, "text", "Efficient"),
        ("qwen/qwen-2.5-72b-instruct", "hub_qwen_balanced", "high", 0.35, 0.4, "text", "General"),
        ("deepseek/deepseek-chat", "hub_deepseek_chat", "medium", 0.14, 0.28, "text", "Budget chat"),
        ("deepseek/deepseek-r1", "hub_deepseek_reasoning", "reasoning_native", 0.55, 2.19, "text", "Reasoning"),
        # xAI via OpenRouter
        ("x-ai/grok-4.20-beta", "hub_xai_frontier", "high", 2.0, 6.0, "text", "Long context"),
        ("x-ai/grok-4.1-fast-non-reasoning", "hub_xai_efficient", "low", 0.2, 0.5, "text", "Fast"),
        # Free-tier (OpenRouter :free — pricing 0; eligibility confirmed via API at runtime)
        ("nvidia/nemotron-3-super-120b-a12b:free", "openrouter_free", "high", 0.0, 0.0, "text", "Free tier; canon openrouter/free"),
        ("arcee-ai/trinity-large-preview:free", "openrouter_free", "medium", 0.0, 0.0, "text", "Free tier"),
        ("google/gemma-3-4b-it:free", "openrouter_free", "low", 0.0, 0.0, "text", "Free tier"),
        ("google/gemma-3-12b-it:free", "openrouter_free", "medium", 0.0, 0.0, "text", "Free tier"),
        ("meta-llama/llama-3.3-70b-instruct:free", "openrouter_free", "high", 0.0, 0.0, "text", "Free tier"),
        ("mistralai/mistral-7b-instruct:free", "openrouter_free", "low", 0.0, 0.0, "text", "Free tier"),
        ("qwen/qwen-2.5-7b-instruct:free", "openrouter_free", "low", 0.0, 0.0, "text", "Free tier"),
        ("deepseek/deepseek-r1-distill-llama-70b:free", "openrouter_free", "reasoning_native", 0.0, 0.0, "text", "Free tier"),
        ("microsoft/phi-3-mini-128k-instruct:free", "openrouter_free", "low", 0.0, 0.0, "text", "Free tier"),
        ("openai/gpt-oss-120b:free", "openrouter_free", "high", 0.0, 0.0, "text", "Free tier"),
        ("openai/gpt-oss-20b:free", "openrouter_free", "medium", 0.0, 0.0, "text", "Free tier"),
        # Extras for digest breadth
        ("z-ai/glm-5", "hub_zai_balanced", "high", 0.5, 2.0, "text", "General"),
        ("stepfun/step-3.5-flash", "hub_stepfun_fast", "medium", 0.2, 0.8, "text", "Fast"),
        ("xiaomi/mimo-v2-pro", "hub_other", "high", 1.0, 4.0, "text", "Alternate hub"),
    ]
    out: list[dict] = []
    for mid, cat, rlevel, inp, outp, mods, note in rows:
        entry: dict = {
            "id": mid,
            "category": cat,
            "reasoning_level": rlevel,
            "modalities": [mods] if mods == "text" else ["text", "image"],
            "pricing": {"usd_per_million_tokens": {"input": inp, "output": outp}},
            "pricing_basis": "openrouter_hub_snapshot_2026-04-13",
            "best_for": [],
            "notes": note,
        }
        if ":free" in mid or cat == "openrouter_free":
            entry["best_for"] = ["Zero-cost exploration", "openrouter/free selector"]
        out.append(entry)
    return out


def main() -> None:
    catalog = {
        "schema_version": 1,
        "snapshot_date": SNAPSHOT_DATE,
        "currency": "USD",
        "disclaimer": (
            "Snapshot for routing assistants. Prices and model availability change frequently. "
            "Always confirm on the provider's official pricing and models pages before relying on costs. "
            "OpenAI pricing rows use the Standard tier unless noted."
        ),
        "sources": [
            {"provider": "openai", "url": "https://platform.openai.com/docs/pricing"},
            {"provider": "anthropic", "url": "https://docs.anthropic.com/en/docs/about-claude/models"},
            {"provider": "anthropic_pricing", "url": "https://docs.anthropic.com/en/about-claude/pricing"},
            {"provider": "xai", "url": "https://docs.x.ai/docs/models"},
            {"provider": "google", "url": "https://ai.google.dev/gemini-api/docs/pricing"},
            {"provider": "google_models", "url": "https://ai.google.dev/gemini-api/docs/models"},
            {"provider": "openrouter", "url": "https://openrouter.ai/docs"},
            {"provider": "openrouter_models", "url": "https://openrouter.ai/models"},
        ],
        "reasoning_level_scale": {
            "none": "No meaningful internal reasoning mode; fastest/cheapest tier for trivial tasks.",
            "low": "Light reasoning; good for classification, extraction, short answers.",
            "medium": "General chat and coding; balances cost and quality.",
            "high": "Strong reasoning and long-context work; default for difficult tasks.",
            "very_high": "Frontier quality; use when failure cost is high.",
            "reasoning_native": "Model family optimized for extended chain-of-thought / reasoning tokens (often higher latency and cost).",
        },
        "cross_provider_routing_hints": [
            "Match task difficulty to reasoning_level first, then optimize cost within that band.",
            "For tool-heavy agent loops, prefer mid-tier fast models (Sonnet, GPT-5.4-mini, Gemini 2.5 Flash, Grok fast) unless a step fails validation.",
            "Use reasoning_native OpenAI o-series or Grok *-reasoning when explicit multi-step deliberation is required and latency is acceptable.",
            "For multimodal + massive context, compare Gemini (1M+ context on 2.5 Flash) vs Claude Opus/Sonnet 4.6 (1M) vs Grok 4 (2M) vs GPT-5.4 family per current docs.",
            "Check deprecation dates (Claude Haiku 3, Gemini 2.0 family) before baking into long-lived routing.",
            "Provider-specific tool surcharges (xAI web_search, Google grounding) can dominate bill; route tool-light tasks to models without forced grounding.",
        ],
        "providers": {
            "openai": {
                "label": "OpenAI",
                "pricing_tiers_note": (
                    "Public pricing lists Standard, Batch (~50% off many models), Flex, and Priority multipliers. "
                    "This catalog uses Standard token rows unless a row is labeled otherwise."
                ),
                "models": _openai_models(),
            },
            "anthropic": {
                "label": "Anthropic",
                "models": _anthropic_models(),
            },
            "xai": {
                "label": "xAI",
                "provider_notes": (
                    "Grok training cutoff Nov 2024 per xAI docs; enable web_search/x_search for current events. "
                    "Batch API: 50% off token costs for text models (see xAI batch docs)."
                ),
                "models": _xai_models(),
                "server_side_tool_surcharges": _xai_tool_pricing(),
            },
            "google": {
                "label": "Google (Gemini API / AI Studio)",
                "models": _google_models(),
            },
            "openrouter": {
                "label": "OpenRouter (aggregate hub)",
                "provider_notes": (
                    "Slugs are provider/model as used on OpenRouter. Paid rows use rough per-1M USD; "
                    ":free rows are 0 in this snapshot — confirm live eligibility via OpenRouter /models."
                ),
                "models": _openrouter_hub_models(),
            },
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
