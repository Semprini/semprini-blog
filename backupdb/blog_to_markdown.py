#!/usr/bin/env python3
"""
Convert a semprini.me blog post to a clean Markdown file.

Dependencies:
    pip install requests beautifulsoup4 markdownify

Standalone usage:
    python blog_to_markdown.py
"""

import re
import requests
from pathlib import Path
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from markdownify import markdownify as md

BASE_URL = "https://www.semprini.me"
DEFAULT_URL = "https://www.semprini.me/2024/08/07/architecting_data_autonomy/"
DEFAULT_OUTPUT = "architecting_data_autonomy.md"

# Matches dated post paths:  /2024/08/07/some-slug/
_DATED_PATH_RE = re.compile(r"^/(\d{4})/(\d{2})/(\d{2})/([^/]+)/?$")

# Matches slug-only paths:   /some-slug/
_SLUG_PATH_RE = re.compile(r"^/([^/]+)/?$")

# Social-share URL fragment
_SOCIAL_RE = re.compile(
    r"(facebook\.com/sharer|twitter\.com/intent|linkedin\.com/shareArticle)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public helpers (also used by crawl_blog.py)
# ---------------------------------------------------------------------------

def fetch_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; blog-to-md/1.0)"}
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.text


def url_to_md_filename(url: str) -> str:
    """
    Convert a dated internal blog post URL to its .md filename.
      https://www.semprini.me/2024/08/07/architecting_data_autonomy/
      -> 2024-08-07_architecting_data_autonomy.md

    Returns None if the URL doesn't match a dated post path.
    """
    path = urlparse(url).path
    m = _DATED_PATH_RE.match(path)
    if m:
        year, month, day, slug = m.groups()
        return f"{year}-{month}-{day}_{slug}.md"
    return None


def _normalise(url: str) -> str:
    """Return a canonical, trailing-slash-stripped URL for dict lookups."""
    return url.rstrip("/").lower()


def build_url_map(post_urls: list[str]) -> dict[str, str]:
    """
    Build a lookup dict that maps every known URL variant of a post
    to its .md filename.

    Keys added per post
    -------------------
    1. Full dated URL   https://www.semprini.me/2024/08/07/slug/
    2. www-less variant https://semprini.me/2024/08/07/slug/
    3. Dated path only  /2024/08/07/slug/
    4. Slug only        /slug/             (covers shorthand links in posts)
    5. Slug bare        slug

    All keys are lower-cased and trailing-slash-stripped for resilient matching.
    """
    url_map: dict[str, str] = {}

    for url in post_urls:
        filename = url_to_md_filename(url)
        if not filename:
            continue

        parsed = urlparse(url)
        m = _DATED_PATH_RE.match(parsed.path)
        if not m:
            continue
        _, _, _, slug = m.groups()

        candidates = [
            url,                                              # full www URL
            url.replace("www.semprini.me", "semprini.me"),   # no-www variant
            parsed.path,                                      # /year/mm/dd/slug/
            f"/{slug}/",                                      # slug-only path
            f"/{slug}",                                       # slug no trailing slash
            slug,                                             # bare slug
        ]
        for c in candidates:
            url_map[_normalise(c)] = filename

    return url_map


def _resolve_href(href: str, url_map: dict[str, str]) -> str | None:
    """
    Given an href from an anchor tag and the url_map, return the local .md
    filename if it resolves to a known post, else return None.

    Tries several normalised key forms so both dated and slug-only links match.
    """
    if not url_map:
        return None

    full = urljoin(BASE_URL, href)
    parsed = urlparse(full)

    # Only rewrite links pointing at this blog
    if parsed.netloc not in ("www.semprini.me", "semprini.me", ""):
        return None

    candidates = [
        _normalise(full),           # full URL
        _normalise(parsed.path),    # just the path
    ]
    # Also try slug extracted from path
    m = _SLUG_PATH_RE.match(parsed.path)
    if m:
        candidates.append(_normalise(m.group(1)))

    for key in candidates:
        if key in url_map:
            return "./" + url_map[key]

    return None


# ---------------------------------------------------------------------------
# Core conversion pipeline
# ---------------------------------------------------------------------------

def extract_title(html: str) -> str:
    """Pull the post title from the <title> tag."""
    soup = BeautifulSoup(html, "html.parser")
    if soup.title:
        return soup.title.get_text(strip=True).split("|")[0].strip()
    return "Untitled"


def extract_article(html: str, url_map: dict[str, str] | None = None) -> BeautifulSoup:
    """
    Parse the HTML and return the article BeautifulSoup node with:
      - navigation / sidebar / comments / social-share elements removed
      - internal blog links rewritten to local .md filenames (needs url_map)
    """
    soup = BeautifulSoup(html, "html.parser")

    # Strip structural chrome
    for selector in [
        "nav", "footer", "header",
        ".related", "#related",
        ".share", ".social",
        ".sidebar", "#sidebar",
        ".comments", "#comments",
        ".disqus", "#disqus_thread",
        ".tags", ".archive",
        "script", "style",
    ]:
        for tag in soup.select(selector):
            tag.decompose()

    # Remove social-share anchor tags
    for a in soup.find_all("a", href=_SOCIAL_RE):
        a.decompose()

    # Remove the post-metadata <ul> block: author / date / category / tag
    # links and the comment count that appears just below the hero image.
    # Any <ul> that contains at least one link to /author/, /category/, or
    # /tag/ is treated as a metadata block and removed entirely.  This also
    # catches the date and comment-count items that travel with those links.
    _META_HREF_RE = re.compile(r"^/(author|category|tag)/", re.IGNORECASE)

    for ul in soup.find_all("ul"):
        if ul.find("a", href=_META_HREF_RE):
            ul.decompose()

    # Rewrite internal links -> relative .md filenames
    for a in soup.find_all("a", href=True):
        resolved = _resolve_href(a["href"], url_map or {})
        if resolved:
            a["href"] = resolved

    article = soup.find("article") or soup.find("main") or soup.find("body")
    return article


def clean_image_urls(soup: BeautifulSoup) -> None:
    """Strip AWS signed-URL query strings so image links stay stable."""
    for img in soup.find_all("img"):
        src = img.get("src", "")
        img["src"] = src.split("?")[0]


def html_to_markdown(article: BeautifulSoup, title: str) -> str:
    """Convert an article node to Markdown with the title as an H1."""
    raw_md = md(
        str(article),
        heading_style="ATX",
        bullets="-",
        strip=["script", "style"],
    )

    # Collapse 3+ blank lines → 2
    raw_md = re.sub(r"\n{3,}", "\n\n", raw_md)

    # Strip residual noise lines
    noise_patterns = [
        r"^\s*\[?(Facebook|Twitter|LinkedIn|Return|Feed RSS)\]?.*$",
        r"^\s*\*\s*(Facebook|Twitter|LinkedIn)\s*$",
        r"^\s*\[Return\].*$",
        r"^\s*Please enable JavaScript.*$",
        r"^\s*blog comments powered by.*$",
        r"^\s*This footer isn.*$",
        r"^\s*\\\*.*$",
    ]
    lines = raw_md.splitlines()
    cleaned = [
        line for line in lines
        if not any(re.match(pat, line, re.IGNORECASE) for pat in noise_patterns)
    ]
    body = "\n".join(cleaned).strip()

    return f"# {title}\n\n{body}\n"


# ---------------------------------------------------------------------------
# Public entry-point used by crawl_blog.py
# ---------------------------------------------------------------------------

def convert(url: str, output_path, url_map: dict[str, str] | None = None) -> None:
    """
    Fetch *url*, convert to Markdown, and write to *output_path*.

    Pass *url_map* (built by crawl_blog.py from all discovered post URLs) so
    that internal links — including slug-only shorthand links — are rewritten
    to relative .md filenames instead of left as HTTP URLs.
    """
    output_path = Path(output_path)
    html = fetch_html(url)
    title = extract_title(html)
    article = extract_article(html, url_map=url_map)
    clean_image_urls(article)
    markdown = html_to_markdown(article, title)
    output_path.write_text(markdown, encoding="utf-8")


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------

def main():
    print(f"Fetching {DEFAULT_URL} ...")
    html = fetch_html(DEFAULT_URL)

    print("Extracting title ...")
    title = extract_title(html)

    print("Parsing article ...")
    # No url_map when run standalone — internal links that can't be resolved
    # will remain as HTTP URLs.
    article = extract_article(html, url_map=None)
    clean_image_urls(article)

    print("Converting to Markdown ...")
    markdown = html_to_markdown(article, title)

    with open(DEFAULT_OUTPUT, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"Done! Saved to '{DEFAULT_OUTPUT}'")


if __name__ == "__main__":
    main()
