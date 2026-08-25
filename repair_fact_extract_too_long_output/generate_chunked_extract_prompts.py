"""Generate bounded citation-extraction prompts for oversized reports."""

import json
import re
from pathlib import Path

from utils.extract import prompt_template, prompt_template_en

RAW_PATH = Path("data/test_data/raw_data/open-deep-research-deepseek-v4-flash-0731-result-260823-1543.jsonl")
OUTPUT_DIR = Path("chunked_extract_prompts")
ARTICLE_IDS = (19, 38, 56, 57, 71, 91, 93)
CHUNK_SIZE = 12_000
OVERLAP = 1_000

SOURCE_HEADING = re.compile(r"^#{1,4}\s+(sources|references|参考文献)\s*$", re.I)
REFERENCE_LINE = re.compile(r"^\[\d+\]")


def split_report(article: str):
    lines = article.splitlines(keepends=True)
    source_start = None
    for i, line in enumerate(lines):
        if SOURCE_HEADING.match(line.strip()):
            source_start = i
            break
    if source_start is None:
        for i, line in enumerate(lines):
            if REFERENCE_LINE.match(line.strip()):
                source_start = i
                break
    if source_start is None:
        raise ValueError("could not locate Sources/References section")

    body = "".join(lines[:source_start]).strip()
    sources = "".join(lines[source_start:]).strip()
    return body, sources


def chunks(text: str):
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        if end < len(text):
            boundary = text.rfind("\n\n", start + CHUNK_SIZE // 2, end)
            if boundary > start:
                end = boundary
        yield text[start:end].strip()
        if end >= len(text):
            break
        start = max(0, end - OVERLAP)


def prompt(language: str, report_text: str) -> str:
    template = prompt_template if language == "zh" else prompt_template_en
    return template.format(report_text=report_text)


def main():
    data = {item["id"]: item for item in (json.loads(line) for line in RAW_PATH.open(encoding="utf-8"))}
    query_path = Path("data/prompt_data/query.jsonl")
    languages = {
        item["id"]: item.get("language")
        for item in (json.loads(line) for line in query_path.open(encoding="utf-8"))
    }
    OUTPUT_DIR.mkdir(exist_ok=True)
    for article_id in ARTICLE_IDS:
        body, sources = split_report(data[article_id]["article"])
        body_chunks = list(chunks(body))
        article_dir = OUTPUT_DIR / f"open_id{article_id}"
        article_dir.mkdir(exist_ok=True)
        for index, body_chunk in enumerate(body_chunks, 1):
            path = article_dir / f"chunk{index:02d}_prompt.txt"
            language = languages.get(article_id)
            if language not in {"zh", "en"}:
                raise ValueError(f"unsupported language for id={article_id}: {language}")
            report_text = f"{body_chunk}\n\n{sources}"
            path.write_text(prompt(language, report_text), encoding="utf-8")
        print(f"id={article_id}: {len(body_chunks)} official prompts -> {article_dir}")


if __name__ == "__main__":
    main()
