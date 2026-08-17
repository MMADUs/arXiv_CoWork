# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import json
from typing import Any


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()

    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()

    start = stripped.find("{")
    end = stripped.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("Response did not contain a JSON object")

    data = json.loads(stripped[start : end + 1])

    if not isinstance(data, dict):
        raise ValueError("Response JSON must be an object")

    return data
