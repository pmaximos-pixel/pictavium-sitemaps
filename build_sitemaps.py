#!/usr/bin/env python3
"""
Image sitemaps for the Pictavium Blogger blogs.

Reads each blog's full post feed, collects every image that appears in each
post, and writes one image sitemap per blog into the "site" folder:

    site/pictavium-images.xml      (www.pictavium.com)
    site/el-pictavium-images.xml   (el.pictavium.com)

Only the Python standard library is used. The Blogger feed must be set to
"Full" (Settings > Site feed), otherwise it carries no images.
"""

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape

BLOGS = [
    ("https://www.pictavium.com", "pictavium-images.xml"),
    ("https://el.pictavium.com", "el-pictavium-images.xml"),
]

OUT_DIR = "site"
PAGE_SIZE = 150          # Blogger's maximum per feed request
MAX_IMAGES_PER_URL = 1000  # Google's limit per <url>

IMG_SRC = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*([\"'])(.*?)\1", re.I | re.S)
A_IMG = re.compile(
    r"<a\b[^>]*?\bhref\s*=\s*([\"'])([^\"']+?)\1[^>]*>\s*<img\b", re.I | re.S
)
IMAGE_HOSTS = ("blogger.googleusercontent.com", "bp.blogspot.com")
IMAGE_EXT = re.compile(r"\.(jpe?g|png|webp|gif|avif)(\?|$)", re.I)


def fetch_json(url, tries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "pictavium-sitemap/1.0"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))


def entries(blog):
    """All published posts of a blog, newest first."""
    start = 1
    while True:
        url = (
            f"{blog}/feeds/posts/default?alt=json"
            f"&max-results={PAGE_SIZE}&start-index={start}"
        )
        feed = fetch_json(url).get("feed", {})
        batch = feed.get("entry", [])
        if not batch:
            return
        yield from batch
        if len(batch) < PAGE_SIZE:
            return
        start += PAGE_SIZE


def is_image_url(u):
    host = urllib.parse.urlsplit(u).netloc.lower()
    return any(host.endswith(h) for h in IMAGE_HOSTS) or bool(IMAGE_EXT.search(u))


def clean(u, page_url):
    u = html.unescape(u.strip())
    if u.startswith("//"):
        u = "https:" + u
    u = urllib.parse.urljoin(page_url, u)
    if u.startswith("http://"):
        u = "https://" + u[len("http://"):]
    return u


def images_in(body, page_url):
    found = []
    # the picture shown in the post
    for _, src in IMG_SRC.findall(body):
        found.append(src)
    # the full-size picture the thumbnail links to (Blogger's default markup)
    for _, href in A_IMG.findall(body):
        found.append(href)
    out, seen = [], set()
    for u in found:
        u = clean(u, page_url)
        if not u.startswith("https://") or u.startswith("data:"):
            continue
        if not is_image_url(u):
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out[:MAX_IMAGES_PER_URL]


def post_url(entry):
    for link in entry.get("link", []):
        if link.get("rel") == "alternate":
            return link.get("href", "")
    return ""


def build(blog, filename):
    rows = []
    total_images = 0
    for e in entries(blog):
        url = post_url(e)
        if not url:
            continue
        body = (e.get("content") or e.get("summary") or {}).get("$t", "")
        imgs = images_in(body, url)
        if not imgs:
            continue
        lastmod = (e.get("updated") or {}).get("$t", "")
        rows.append((url, lastmod, imgs))
        total_images += len(imgs)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ]
    for url, lastmod, imgs in rows:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(url)}</loc>")
        if lastmod:
            lines.append(f"    <lastmod>{escape(lastmod)}</lastmod>")
        for i in imgs:
            lines.append(f"    <image:image><image:loc>{escape(i)}</image:loc></image:image>")
        lines.append("  </url>")
    lines.append("</urlset>")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, filename), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{blog}: {len(rows)} posts with images, {total_images} images -> {filename}")
    return len(rows)


def main():
    failed = False
    for blog, filename in BLOGS:
        try:
            if build(blog, filename) == 0:
                print(f"WARNING: no images found for {blog}. Is the site feed set to Full?")
        except Exception as exc:
            failed = True
            print(f"ERROR building {blog}: {exc}", file=sys.stderr)
    # a page that tells a visitor what this site is
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(
            "<!doctype html><meta charset='utf-8'><title>Pictavium image sitemaps</title>"
            "<p><a href='pictavium-images.xml'>www.pictavium.com</a></p>"
            "<p><a href='el-pictavium-images.xml'>el.pictavium.com</a></p>\n"
        )
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
