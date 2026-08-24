import multiprocessing
import json
import os
import time
import argparse
import platform
from tqdm import tqdm
from .api import scrape_url
from .io_utils import load_jsonl


MAX_RETRIES = int(os.environ.get('SCRAPE_MAX_RETRIES', '3'))
RETRY_DELAY_SECONDS = float(os.environ.get('SCRAPE_RETRY_DELAY', '1'))
BALANCE_EXHAUSTED = False


def scrape(citation_url):
    global BALANCE_EXHAUSTED

    # Each pool worker stops issuing requests after it observes a balance error.
    if BALANCE_EXHAUSTED:
        return {
            'url': citation_url,
            'error': 'balance exhausted',
        }

    retries = 0
    while retries < MAX_RETRIES:
        result = scrape_url(citation_url)
        retries += 1
        if 'error' not in result:
            break
        if 'balance' in result['error'].lower():
            print('\033[91mkey 已经没有额度，请更换 key\033[0m', flush=True)
            BALANCE_EXHAUSTED = True
            break
        if retries < MAX_RETRIES:
            # Back off between retries so transient 524s do not create a
            # burst of duplicate requests to the Reader API.
            time.sleep(min(RETRY_DELAY_SECONDS * (2 ** (retries - 1)), 30))

    if 'error' not in result:
        title = result.get('title', '')
        content = result.get('content', '')
        description = result.get('description', '')
        url_content = f"{title}\n\n{description}\n\n{content}"
        return {'url': citation_url, 'url_content': url_content}

    return {
        'url': citation_url,
        'error': result.get('error', 'unknown error'),
    }


def has_successful_content(citation):
    content = citation.get('url_content', '')
    return bool(content) and not content.startswith('scrape failed:')


def append_checkpoint(checkpoint_path, task_id, result):
    checkpoint = {
        'id': task_id,
        'url': result['url'],
        'url_content': result['url_content'],
    }
    with open(checkpoint_path, 'a+', encoding='utf-8') as f:
        f.write(json.dumps(checkpoint, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def append_failed_url(failure_path, url, error):
    with open(failure_path, 'a+', encoding='utf-8') as f:
        f.write(json.dumps({'url': url, 'error': error}, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def write_article(output_path, d):
    # Replace any existing line with the same article id so that scraped.jsonl
    # keeps exactly one (latest) entry per article across resume runs.
    article_id = d['id']
    new_line = json.dumps(d, ensure_ascii=False) + "\n"
    if os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    else:
        lines = []
    kept = [
        line for line in lines
        if json.loads(line).get('id') != article_id
    ]
    kept.append(new_line)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(kept)
        f.flush()
        os.fsync(f.fileno())


if __name__ == '__main__':
    if platform.system() == 'Darwin':  
        try:
            multiprocessing.set_start_method('spawn')
        except RuntimeError:
            pass
    else: 
        try:
            multiprocessing.set_start_method('fork')
        except RuntimeError:
            pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--output_path", type=str, required=True)
    parser.add_argument("--raw_data_path", type=str, required=True)
    parser.add_argument("--n_total_process", type=int, default=1)
    args = parser.parse_args()
    
    output_path = args.output_path
    checkpoint_path = f"{output_path}.progress.jsonl"
    failure_path = f"{output_path}.failed_urls.jsonl"
    
    # initialize variables
    raw_data = []
    data_to_process = []
    processed = []
    checkpoints = {}
    failed_urls = {}
    
    try:
        raw_data = load_jsonl(args.raw_data_path)
        
        if os.path.exists(output_path):
            completed_data = load_jsonl(output_path)
            for previous in completed_data:
                for url, citation in previous['citations_deduped'].items():
                    if has_successful_content(citation):
                        checkpoints.setdefault(previous['id'], {})[url] = citation['url_content']
            processed = [
                d['id'] for d in completed_data
                if all(has_successful_content(v) for v in d['citations_deduped'].values())
            ]

        if os.path.exists(checkpoint_path):
            for checkpoint in load_jsonl(checkpoint_path):
                checkpoints.setdefault(checkpoint['id'], {})[checkpoint['url']] = checkpoint['url_content']

        if os.path.exists(failure_path):
            for failure in load_jsonl(failure_path):
                failed_urls[failure['url']] = failure.get('error', 'previous scrape failure')

        data_to_process = [d for d in raw_data if d['id'] not in processed]
    except Exception as exc:
        import sys
        print(f"cannot process file {args.raw_data_path}: {exc}")
        sys.exit(f'{args.raw_data_path} has not been processed yet...')
    
    print(f"processing {len(data_to_process)} instances...")

    for d in tqdm(data_to_process):
        for url, content in checkpoints.get(d['id'], {}).items():
            if url in d['citations_deduped']:
                d['citations_deduped'][url]['url_content'] = content

        for url, error in failed_urls.items():
            if url in d['citations_deduped'] and not has_successful_content(d['citations_deduped'][url]):
                d['citations_deduped'][url]['url_content'] = f"scrape failed: cached failure: {error}"

        # get the citations that need to be scraped
        citations = [
            url for url, citation in d['citations_deduped'].items()
            if not has_successful_content(citation) and url not in failed_urls
        ]
        results = []

        n_total_process = min(args.n_total_process, len(citations))

        if n_total_process == 1:
            for citation in citations:
                result = scrape(citation)
                content = (
                    f"scrape failed: {result['error']}"
                    if 'error' in result
                    else result['url_content']
                )
                d['citations_deduped'][result['url']]['url_content'] = content
                append_checkpoint(checkpoint_path, d['id'], {
                    'url': result['url'], 'url_content': content,
                })
                if 'error' in result and 'balance' not in result['error'].lower():
                    failed_urls[result['url']] = result['error']
                    append_failed_url(failure_path, result['url'], result['error'])
        elif n_total_process > 1:
            with multiprocessing.Pool(processes=n_total_process) as pool:
                results = pool.map(scrape, citations)

        # update the url_content
        for res in results:
            content = (
                f"scrape failed: {res['error']}"
                if 'error' in res
                else res['url_content']
            )
            d['citations_deduped'][res['url']]['url_content'] = content
            append_checkpoint(checkpoint_path, d['id'], {
                'url': res['url'], 'url_content': content,
            })
            if 'error' in res and 'balance' not in res['error'].lower():
                failed_urls[res['url']] = res['error']
                append_failed_url(failure_path, res['url'], res['error'])

        # write the updated data to the output file, replacing any
        # previous entry for the same article id
        write_article(output_path, d)

    if os.path.exists(output_path):
        final_data = load_jsonl(output_path)
        total_urls = sum(len(d['citations_deduped']) for d in final_data)
        successful_urls = sum(
            has_successful_content(citation)
            for d in final_data
            for citation in d['citations_deduped'].values()
        )
        ratio = successful_urls / total_urls if total_urls else 0
        print(
            f"scrape success: {successful_urls}/{total_urls} "
            f"({ratio:.2%})"
        )
