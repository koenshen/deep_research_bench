"""Merge chunk extraction outputs by article id without touching extracted.jsonl."""

import argparse
import json
from pathlib import Path


ARTICLE_IDS = (19, 38, 56, 57, 71, 91, 93)


def load_json(path: Path):
    text = path.read_text(encoding="utf-8").replace("```json", "").replace("```", "").strip()
    if not text:
        return []
    value = json.loads(text)
    if not isinstance(value, list):
        raise ValueError(f"expected a JSON list: {path}")
    return value


def merge_article(article_id: int, prompt_dir: Path, output_dir: Path) -> None:
    article_dir = prompt_dir / f"open_id{article_id}"
    files = sorted(article_dir.glob("chunk*_output.txt"))
    if not files:
        raise ValueError(f"no chunk outputs found: {article_dir}")

    merged = []
    seen = set()
    raw_count = 0
    duplicate_count = 0
    malformed = []
    for path in files:
        try:
            records = load_json(path)
        except Exception as exc:
            malformed.append(f"{path.name}: {exc}")
            continue
        raw_count += len(records)
        for record in records:
            if not isinstance(record, dict):
                malformed.append(f"{path.name}: non-object record")
                continue
            missing = {"fact", "ref_idx", "url"} - set(record)
            if missing:
                malformed.append(f"{path.name}: missing {sorted(missing)}")
                continue
            key = (record["fact"], str(record["ref_idx"]), record["url"])
            if key in seen:
                duplicate_count += 1
                continue
            seen.add(key)
            merged.append(record)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"open_id{article_id}_merged.json"
    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    bad_urls = [
        (i, record.get("url", ""))
        for i, record in enumerate(merged)
        if not isinstance(record.get("url"), str) or not record.get("url", "").startswith(("http://", "https://"))
    ]
    print(
        f"id={article_id}: chunks={len(files)}, raw={raw_count}, "
        f"deduplicated={len(merged)}, duplicates_removed={duplicate_count}, "
        f"bad_urls={len(bad_urls)}, output={output_path}"
    )
    for item in malformed:
        print(f"  warning: {item}")
    for index, url in bad_urls[:5]:
        print(f"  warning: record {index} has invalid URL: {url!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt_dir", type=Path, default=Path("chunked_extract_prompts"))
    parser.add_argument("--output_dir", type=Path, default=Path("chunked_extract_merged"))
    parser.add_argument("--article_id", type=int, choices=ARTICLE_IDS)
    args = parser.parse_args()

    ids = (args.article_id,) if args.article_id is not None else ARTICLE_IDS
    for article_id in ids:
        merge_article(article_id, args.prompt_dir, args.output_dir)


if __name__ == "__main__":
    main()
