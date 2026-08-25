"""Run chunked extraction prompts sequentially and save each response."""

import argparse
import os
import time
from pathlib import Path


ARTICLE_IDS = (19, 38, 56, 57, 71, 91, 93)


def run_one(prompt_path: Path, retries: int, call_model) -> bool:
    output_path = prompt_path.with_name(prompt_path.name.replace("_prompt.txt", "_output.txt"))
    prompt = prompt_path.read_text(encoding="utf-8")
    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"skip existing: {output_path}", flush=True)
        return True

    for attempt in range(1, retries + 1):
        started = time.monotonic()
        print(
            f"requesting {prompt_path} attempt {attempt}/{retries} "
            f"({len(prompt)} prompt chars)",
            flush=True,
        )
        try:
            result = call_model(prompt)
            temporary = output_path.with_suffix(output_path.suffix + ".tmp")
            temporary.write_text(result, encoding="utf-8")
            temporary.replace(output_path)
            print(
                f"completed {output_path}: {len(result)} response chars, "
                f"{time.monotonic() - started:.1f}s",
                flush=True,
            )
            return True
        except Exception as exc:
            print(
                f"failed {prompt_path} after {time.monotonic() - started:.1f}s: {exc}",
                flush=True,
            )
            if attempt < retries:
                delay = 2 ** (attempt - 1)
                print(f"retrying in {delay}s", flush=True)
                time.sleep(delay)
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt_dir", type=Path, default=Path("chunked_extract_prompts"))
    parser.add_argument(
        "--article_id",
        type=int,
        choices=ARTICLE_IDS,
        help="Process only one article id; default processes all article ids.",
    )
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files.")
    args = parser.parse_args()
    if args.retries < 1:
        parser.error("--retries must be at least 1")

    required = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "FACT_MODEL")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        parser.error("missing environment variable(s): " + ", ".join(missing))

    # utils.api reads backend selection at import time.
    os.environ.setdefault("LLM_BACKEND", "openai")
    from utils.api import call_model

    print(
        f"start: backend=openai, model={os.environ['FACT_MODEL']}, "
        f"base_url={os.environ['OPENAI_BASE_URL']}, articles={len(ARTICLE_IDS)}",
        flush=True,
    )
    failures = []
    article_ids = (args.article_id,) if args.article_id is not None else ARTICLE_IDS
    for article_id in article_ids:
        article_dir = args.prompt_dir / f"open_id{article_id}"
        prompts = sorted(article_dir.glob("chunk*_prompt.txt"))
        if not prompts:
            failures.append(article_dir)
            print(f"no prompts found: {article_dir}", flush=True)
            continue
        for prompt_path in prompts:
            output_path = prompt_path.with_name(prompt_path.name.replace("_prompt.txt", "_output.txt"))
            if args.force and output_path.exists():
                output_path.unlink()
            if not run_one(prompt_path, args.retries, call_model):
                failures.append(prompt_path)

    if failures:
        raise SystemExit("failed: " + ", ".join(map(str, failures)))
    print("all chunk prompts completed", flush=True)


if __name__ == "__main__":
    main()
