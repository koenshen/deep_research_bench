import json
from pathlib import Path
from typing import Any
from crw import CrwClient
from url_normalize import url_normalize
def main() -> None:
    client = CrwClient(api_key="your_key")
    path = Path("results/fact/open-deep-research-deepseek-v4-flash-0731-result-260823-1543/scraped.jsonl.failed_urls.jsonl")
    rescraped_path = Path("_rescraped.json")
    rescraped: dict[str, Any] = {}
    if rescraped_path.exists():
        rescraped = json.loads(rescraped_path.read_text())
    lines = path.read_text().splitlines()
    all_urls = [json.loads(line)["url"] for line in lines]
    canonical_map: dict[str, str] = {}
    reverse_map: dict[str, str] = {}
    invalid_urls: set[str] = set()
    for url in all_urls:
        try:
            norm = url_normalize(url)
        except (TypeError, ValueError) as exc:
            print(f"Failed: {url}: invalid URL ({exc})")
            invalid_urls.add(url)
            continue
        if norm is None:
            print(f"Failed: {url}: could not canonicalize URL")
            invalid_urls.add(url)
            continue
        canonical_map[url] = norm
        reverse_map[norm] = url
    for url in invalid_urls:
        rescraped[url] = "failed"
    if invalid_urls:
        rescraped_path.write_text(json.dumps(rescraped, ensure_ascii=False, indent=2))
    urls: list[str] = [url for url in all_urls if url not in rescraped]
    print(f"{len(urls)}/{len(all_urls)} URL(s) to be processed...")
    for i, url in enumerate(urls):
        print(f"Scraping URL {i + 1}/{len(urls)}: {url}")
        canon = canonical_map.get(url)
        if not canon:
            rescraped[url] = "failed"
            continue
        try:
            result = client.scrape(
                canon,
                formats=["markdown"],
                only_main_content=True,
            )
            raw = result.get("metadata", {}).get("sourceURL", canon)
            rescraped[reverse_map.get(raw, url)] = result
        except Exception as exc:
            print(f"Failed: {url}: {exc}")
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
