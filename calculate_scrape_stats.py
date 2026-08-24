"""Calculate scrape success statistics for the configured benchmark output."""

import json
import os
from pathlib import Path


def main() -> None:
    model = os.environ.get("MODEL")
    output_dir = os.environ.get("OUT")

    if not output_dir:
        if not model:
            raise SystemExit(
                "Please export MODEL or OUT first, for example: "
                'export MODEL="..."'
            )
        output_dir = f"results/fact/{model}"

    scraped_path = Path(output_dir) / "scraped.jsonl"
    if not scraped_path.is_file():
        raise SystemExit(f"scraped file not found: {scraped_path}")

    total = 0
    successful = 0
    articles = 0

    with scraped_path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                article = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    f"invalid JSON in {scraped_path}:{line_number}: {exc}"
                ) from exc

            articles += 1
            citations = article.get("citations_deduped", {})
            for citation in citations.values():
                total += 1
                content = citation.get("url_content", "")
                if content and not content.startswith("scrape failed:"):
                    successful += 1

    ratio = successful / total if total else 0.0
    print(f"model: {model or '<from OUT>'}")
    print(f"scraped file: {scraped_path}")
    print(f"articles: {articles}")
    print(f"successful URLs: {successful}")
    print(f"total URLs: {total}")
    print(f"success rate: {ratio:.2%}")


if __name__ == "__main__":
    main()
# export MODEL="gpt-researcher-deepseek-v4-flash-0731-result-260822"
# python calculate_scrape_stats.py