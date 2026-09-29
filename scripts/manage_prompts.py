from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

load_dotenv()

from langfuse import get_client  # noqa: E402  (must load .env before client init)

PROMPT_NAME = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")

V1 = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
V2 = V1 + "\nAnswer in one concise paragraph."


def _set_labels(client, version: int, labels: list[str]) -> None:
    client.update_prompt(name=PROMPT_NAME, version=version, new_labels=labels)
    print(f"{PROMPT_NAME} v{version} labels -> {labels}")


def create() -> None:
    client = get_client()
    try:
        existing = client.get_prompt(PROMPT_NAME, type="text", max_retries=0)
        print(f"Prompt '{PROMPT_NAME}' already exists (version {existing.version}); skipping create.")
        return
    except Exception:
        pass

    v1 = client.create_prompt(
        name=PROMPT_NAME,
        type="text",
        prompt=V1,
        labels=["baseline", "production"],
        commit_message="v1 baseline",
    )
    v2 = client.create_prompt(
        name=PROMPT_NAME,
        type="text",
        prompt=V2,
        labels=["candidate"],
        commit_message="v2 candidate",
    )
    print(f"Created {v1.name} v{v1.version} (baseline, production) and v{v2.version} (candidate)")


def promote() -> None:
    client = get_client()
    _set_labels(client, 2, ["candidate", "production"])
    _set_labels(client, 1, ["baseline"])


def rollback() -> None:
    client = get_client()
    _set_labels(client, 1, ["baseline", "production"])
    _set_labels(client, 2, ["candidate"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed and promote/rollback the day13-chat prompt")
    parser.add_argument("action", choices=["create", "promote", "rollback"])
    args = parser.parse_args()

    {"create": create, "promote": promote, "rollback": rollback}[args.action]()


if __name__ == "__main__":
    main()
