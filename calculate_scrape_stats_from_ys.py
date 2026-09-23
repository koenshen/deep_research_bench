import json
from pathlib import Path
from typing import Any
from crw import CrwClient
from url_normalize import url_normalize
def main() -> None:
    client = CrwClient(api_key="your_key")
    path = Path("results/fact/gpt-researcher-deepseek-v4-flash-0731-result-260822/scraped.jsonl.failed_urls.jsonl")
    rescraped_path = Path("_rescraped.json")
    rescraped: dict[str, Any] = {}
    if rescraped_path.exists():
        rescraped = json.loads(rescraped_path.read_text())
    lines = path.read_text().splitlines()
    all_urls = [json.loads(line)["url"] for line in lines]
    canonical_map: dict[str, str] = {}
    reverse_map: dict[str, str] = {}
    for url in all_urls:
        norm = url_normalize(url)
        if norm is None:
            print(f"Warning: failed to canonicalize {url}")
            continue
        canonical_map[url] = norm
        reverse_map[norm] = url
    urls: list[str] = [url for url in all_urls if url not in rescraped]
    print(f"{len(urls)}/{len(all_urls)} URL(s) to be processed...")
    BATCH_SIZE = 5
    for i in range(0, len(urls), BATCH_SIZE):
        batch = urls[i : i + BATCH_SIZE]
        print(f"Scraping batch: {i} through {min(i + BATCH_SIZE, len(urls))}...")
        results = client.batch_scrape(
            [canon for url in batch if (canon := canonical_map.get(url))],
            formats=["markdown"],
            only_main_content=True,
        )
        for res in results:
            raw: str = res["metadata"]["sourceURL"]
            rescraped[reverse_map.get(raw, raw)] = res
        for url in batch:
            if url not in rescraped:
                rescraped[url] = "failed"
        rescraped_path.write_text(json.dumps(rescraped, ensure_ascii=False, indent=2))
    ok: int = 0
    for k, v in rescraped.items():
        if v == "failed":
            print(f"{k}: Unknown Error")
        elif "markdown" not in v:
            print(f"{k}: {v['warning']}")
        else:
            ok += 1
    print(f"Successful: {ok}/{len(rescraped)}\n")
    extras = rescraped.keys() - set(all_urls)
    if extras:
        print("Extra URL(s) processed by CRW, please check manually:")
        for url in extras:
            print(url)
if __name__ == "__main__":
    main()