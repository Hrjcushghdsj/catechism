#!/usr/bin/env python3
"""
inline_json.py

Usage:
    python inline_json.py -i input.html -o output.html

Reads an HTML file containing:
    const CCC_JSON_URL  = '...';
    const REFS_JSON_URL = '...';

Fetches each URL, then rewrites the file so that:
    const CCC_JSON_INLINE  = {...};
    const REFS_JSON_INLINE = {...};

are populated with the fetched JSON. The *_URL constants are left untouched.
"""

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path


# Match `const NAME = 'value';` or `const NAME = "value";` or `const NAME = null;`
def find_const(html: str, name: str):
    pattern = re.compile(
        r"const\s+" + re.escape(name) + r"\s*=\s*(null|'[^']*'|\"[^\"]*\")\s*;"
    )
    m = pattern.search(html)
    if not m:
        return None
    return m


def get_url_from_value(raw: str):
    raw = raw.strip()
    if raw == "null":
        return None
    # strip surrounding quotes
    return raw[1:-1]


def fetch_json(url: str):
    print(f"  fetching {url}", file=sys.stderr)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "inline_json/1.0 (+https://example.invalid)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    return json.loads(data)


def replace_const(html: str, name: str, json_value) -> str:
    """Replace `const NAME = ...;` with an inline JSON assignment."""
    # Serialize compactly but on one line; escape backslashes/backticks not needed
    # because we're using a normal JS object literal, not a template string.
    serialized = json.dumps(json_value, ensure_ascii=False, separators=(",", ":"))

    # We use a regex to find the original declaration so we can replace it in place.
    pattern = re.compile(
        r"const\s+" + re.escape(name) + r"\s*=\s*(null|'[^']*'|\"[^\"]*\")\s*;"
    )
    replacement = f"const {name} = {serialized};"
    new_html, n = pattern.subn(replacement, html, count=1)
    if n == 0:
        raise RuntimeError(f"Could not find declaration for {name}")
    return new_html


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-i", "--input", required=True, help="Input HTML file")
    ap.add_argument("-o", "--output", required=True, help="Output HTML file")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.is_file():
        sys.exit(f"Input file not found: {src}")

    html = src.read_text(encoding="utf-8")

    # ---- Resolve the two URLs ----
    jobs = [
        ("CCC_JSON_URL",  "CCC_JSON_INLINE"),
        ("REFS_JSON_URL", "REFS_JSON_INLINE"),
    ]

    fetched = {}
    for url_name, inline_name in jobs:
        m = find_const(html, url_name)
        if not m:
            print(f"  warning: no {url_name} declaration found, skipping", file=sys.stderr)
            continue
        url = get_url_from_value(m.group(1))
        if not url:
            print(f"  {url_name} is null/empty, skipping", file=sys.stderr)
            continue
        print(f"-> {url_name} = {url}", file=sys.stderr)
        try:
            fetched[inline_name] = fetch_json(url)
        except urllib.error.HTTPError as e:
            sys.exit(f"HTTP error fetching {url}: {e.code} {e.reason}")
        except urllib.error.URLError as e:
            sys.exit(f"Network error fetching {url}: {e.reason}")
        except json.JSONDecodeError as e:
            sys.exit(f"Invalid JSON at {url}: {e}")

    if not fetched:
        sys.exit("Nothing to inline (no URLs could be resolved).")

    # ---- Inline ----
    out_html = html
    for inline_name, value in fetched.items():
        print(f"-> inlining {inline_name} ({len(json.dumps(value))} bytes)", file=sys.stderr)
        out_html = replace_const(out_html, inline_name, value)

    dst = Path(args.output)
    dst.write_text(out_html, encoding="utf-8")
    print(f"Wrote {dst} ({len(out_html)} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()