"""Repair invalid JSON escapes in completed chunk outputs."""

import json
from pathlib import Path


FILES = (
    Path("chunked_extract_prompts/open_id19/chunk02_output.txt"),
    Path("chunked_extract_prompts/open_id56/chunk01_output.txt"),
    Path("chunked_extract_prompts/open_id56/chunk02_output.txt"),
    Path("chunked_extract_prompts/open_id93/chunk04_output.txt"),
)


def repair_escapes(text: str) -> str:
    out = []
    i = 0
    valid = '"\\/bfnrt'
    while i < len(text):
        if text[i] != "\\":
            out.append(text[i])
            i += 1
            continue
        if i + 1 >= len(text):
            out.append("\\\\")
            break
        nxt = text[i + 1]
        if nxt == "u" and i + 5 < len(text) and all(
            c in "0123456789abcdefABCDEF" for c in text[i + 2:i + 6]
        ):
            out.append(text[i:i + 6])
            i += 6
        elif nxt in valid:
            out.append(text[i:i + 2])
            i += 2
        elif nxt == "'":
            out.append("'")
            i += 2
        else:
            out.append("\\\\" + nxt)
            i += 2
    return "".join(out)


for path in FILES:
    text = path.read_text(encoding="utf-8").replace("```json", "").replace("```", "").strip()
    repaired = repair_escapes(text)
    data = json.loads(repaired)
    if not isinstance(data, list):
        raise ValueError(f"expected JSON list in {path}")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"repaired {path}: {len(data)} records")
