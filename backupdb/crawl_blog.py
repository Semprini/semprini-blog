#!/usr/bin/env python3
"""
Crawl all blog index pages on https://www.semprini.me, discover every post
URL, and convert each one to a Markdown file by reusing the functions in
blog_to_markdown.py.

Dependencies:
    pip install requests beautifulsoup4 markdownify

Usage:
    # Both scripts must be in the same directory.
    python crawl_blog.py

    # Optional flags
    python crawl_blog.py --output-dir ./markdown_posts
    python crawl_blog.py --delay 2          # seconds between requests (default 1)
    python crawl_blog.py --skip-existing    # don't re-convert already saved files
"""

import argparse
import importlib.util
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup  # used for index-page parsing

# ---------------------------------------------------------------------------
# Load blog_to_markdown as a module from the same directory as this script
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent
_BTM_PATH = _SCRIPT_DIR / "blog_to_markdown.py"

if not _BTM_PATH.exists():
    sys.exit(
        f"ERROR: Could not find 'blog_to_markdown.py' in {_SCRIPT_DIR}\n"
        "Please make sure both scripts are in the same directory."
    )

spec = importlib.util.spec_from_file_location("blog_to_markdown", _BTM_PATH)
btm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(btm)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL = "https://www.semprini.me"
INDEX_URL = BASE_URL + "/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; blog-crawler/1.0)"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch(url: str) -> str:
    """Fetch a URL and return its HTML text."""
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.text


def discover_index_pages(first_page_html: str) -> list[str]:
    """
    Parse the first index page and return all paginated index URLs,
    including the first page itself, sorted by page number.
    """
    soup = BeautifulSoup(first_page_html, "html.parser")
    pages = [INDEX_URL]

    for a in soup.find_all("a", href=re.compile(r"\?page=\d+")):
        full = urljoin(BASE_URL, a["href"])
        if full not in pages:
            pages.append(full)

    def page_num(url: str) -> int:
        m = re.search(r"page=(\d+)", url)
        return int(m.group(1)) if m else 0

    pages.sort(key=page_num)
    return pages


def extract_post_urls(index_html: str) -> list[str]:
    """
    Pull dated blog-post URLs from a single index page.
    Posts follow the pattern: /<year>/<month>/<day>/<slug>/
    """
    soup = BeautifulSoup(index_html, "html.parser")
    post_pattern = re.compile(r"^/\d{4}/\d{2}/\d{2}/[^/]+/?$")
    seen: set[str] = set()
    urls: list[str] = []

    for a in soup.find_all("a", href=post_pattern):
        full = urljoin(BASE_URL, a["href"])
        if full not in seen:
            seen.add(full)
            urls.append(full)

    return urls


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Crawl semprini.me and convert every blog post to Markdown."
    )
    parser.add_argument(
        "--output-dir", default="markdown_posts",
        help="Directory to save .md files (default: ./markdown_posts)"
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds to wait between HTTP requests (default: 1)"
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip posts whose output file already exists"
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- Step 1: discover all index pages ----
    print(f"Fetching index: {INDEX_URL}")
    first_html = fetch(INDEX_URL)
    index_pages = discover_index_pages(first_html)
    print(f"Found {len(index_pages)} index page(s): {index_pages}")

    # ---- Step 2: collect all post URLs from every index page ----
    all_post_urls: list[str] = []
    seen_posts: set[str] = set()

    for i, page_url in enumerate(index_pages):
        if i == 0:
            page_html = first_html
        else:
            print(f"\nFetching index page {i + 1}: {page_url}")
            time.sleep(args.delay)
            page_html = fetch(page_url)

        post_urls = extract_post_urls(page_html)
        new_urls = [u for u in post_urls if u not in seen_posts]
        seen_posts.update(new_urls)
        all_post_urls.extend(new_urls)
        print(f"  -> {len(new_urls)} post(s) found on this page")

    print(f"\nTotal posts discovered: {len(all_post_urls)}")

    # ---- Step 3: build url_map so internal links resolve to .md files ----
    # The map covers dated URLs, www/no-www variants, and slug-only shorthand
    # links — see build_url_map() in blog_to_markdown.py for full details.
    url_map = btm.build_url_map(all_post_urls)
    print(f"URL map built: {len(url_map)} key(s) covering {len(all_post_urls)} post(s)")

    # ---- Step 4: convert each post ----
    success, skipped, failed = 0, 0, 0

    for idx, url in enumerate(all_post_urls, start=1):
        filename = btm.url_to_md_filename(url)
        if not filename:
            print(f"[{idx}/{len(all_post_urls)}] SKIP (no filename derived): {url}")
            skipped += 1
            continue

        output_path = output_dir / filename

        if args.skip_existing and output_path.exists():
            print(f"[{idx}/{len(all_post_urls)}] SKIP (exists): {filename}")
            skipped += 1
            continue

        print(f"[{idx}/{len(all_post_urls)}] Converting: {url}")
        time.sleep(args.delay)

        try:
            # Pass url_map so internal links become ./YYYY-MM-DD_slug.md
            btm.convert(url, output_path, url_map=url_map)
            print(f"    OK -> {output_path}")
            success += 1
        except Exception as exc:
            print(f"    FAILED: {exc}")
            failed += 1

    # ---- Summary ----
    print(f"\n{'='*50}")
    print(f"Done. {success} converted, {skipped} skipped, {failed} failed.")
    print(f"Output directory: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
