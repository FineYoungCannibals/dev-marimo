#!/usr/bin/env python3
"""Refresh ai.models.custom_models/displayed_models in .marimo.toml from a
provider's live /models listing, instead of hand-maintaining model IDs.

Usage:
    python scripts/refresh_ai_models.py
    python scripts/refresh_ai_models.py --provider ollama --config /opt/docker/marimo/.marimo.toml
    python scripts/refresh_ai_models.py --update-chat-model
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
import tomlkit

# Labels lemonade attaches to models that can't serve chat completions.
NON_CHAT_LABELS = {"embeddings", "transcription", "realtime-transcription"}


def is_chat_capable(entry: dict) -> bool:
    if entry.get("downloaded") is False:
        return False
    labels = entry.get("labels")
    if labels is None:
        # Provider doesn't return labels (e.g. plain Ollama) -- nothing to
        # filter on, assume it's usable.
        return True
    return not NON_CHAT_LABELS.intersection(labels)


def get_base_url(doc: tomlkit.TOMLDocument, provider: str) -> str:
    ai = doc.get("ai", {})
    if provider == "ollama":
        base_url = ai.get("ollama", {}).get("base_url")
    else:
        base_url = ai.get("custom_providers", {}).get(provider, {}).get("base_url")
    if not base_url:
        sys.exit(
            f"No base_url found for provider {provider!r} in the config. "
            f"Expected [ai.custom_providers.{provider}] or [ai.{provider}]."
        )
    return base_url.rstrip("/")


def fetch_model_ids(base_url: str) -> list[str]:
    resp = httpx.get(f"{base_url}/models", timeout=10)
    resp.raise_for_status()
    entries = resp.json()["data"]
    return [e["id"] for e in entries if is_chat_capable(e)]


def refresh(config_path: Path, provider: str, update_chat_model: bool) -> None:
    doc = tomlkit.parse(config_path.read_text())
    base_url = get_base_url(doc, provider)

    print(f"Querying {base_url}/models ...")
    model_ids = fetch_model_ids(base_url)
    if not model_ids:
        sys.exit(f"No chat-capable models reported by {provider!r} at {base_url}.")
    qualified = [f"{provider}/{m}" for m in sorted(model_ids)]
    print(f"Found {len(qualified)} chat-capable model(s): {', '.join(qualified)}")

    ai_models = doc["ai"]["models"]
    prefix = f"{provider}/"

    for key in ("custom_models", "displayed_models"):
        existing = list(ai_models.get(key, []))
        kept = [m for m in existing if not m.startswith(prefix)]
        ai_models[key] = kept + qualified

    for role in ("chat_model", "edit_model", "autocomplete_model"):
        current = ai_models.get(role)
        if not current or not current.startswith(prefix):
            continue
        if current in qualified:
            continue
        print(
            f"WARNING: {role} = {current!r} is no longer reported by {provider!r}. "
            f"Available: {', '.join(qualified)}"
        )
        if update_chat_model and role == "chat_model":
            ai_models[role] = qualified[0]
            print(f"  -> updated chat_model to {qualified[0]!r}")

    config_path.write_text(tomlkit.dumps(doc))
    print(f"Wrote {config_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent.parent / ".marimo.toml",
        help="Path to .marimo.toml (default: repo root .marimo.toml)",
    )
    parser.add_argument(
        "--provider",
        default="lemonade",
        help="Provider name as it appears under ai.custom_providers, or 'ollama' (default: lemonade)",
    )
    parser.add_argument(
        "--update-chat-model",
        action="store_true",
        help="If the configured chat_model is no longer available, replace it with the first discovered model",
    )
    args = parser.parse_args()

    if not args.config.exists():
        sys.exit(f"{args.config} does not exist")

    refresh(args.config, args.provider, args.update_chat_model)


if __name__ == "__main__":
    main()
