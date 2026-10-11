#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "feedparser",
# ]
# ///
"""Fetch OPML-configured RSS and Atom feeds with feedparser."""

from calendar import timegm
from datetime import datetime, timezone
import argparse
import http.client
import json
from pathlib import Path
import sys
from urllib.error import URLError
from xml.etree import ElementTree

import feedparser

UTC = timezone.utc
SUMMARY_MAX_LENGTH = 1_000


def load_opml(path):
    try:
        root = ElementTree.fromstring(Path(path).read_text(encoding="utf-8"))
    except ElementTree.ParseError as error:
        raise ValueError(f"invalid XML: {error}") from error
    namespace, _, name = root.tag.rpartition("}")
    if name != "opml":
        raise ValueError("document root must be opml")
    if root.get("version") != "2.0":
        raise ValueError("OPML version must be 2.0")
    namespaces = {"": namespace[1:]} if namespace else {}
    body = root.find("body", namespaces)
    if body is None:
        raise ValueError("OPML body is required")
    feeds = []
    _collect_feeds(body, feeds, namespaces)
    if not feeds:
        raise ValueError("OPML must contain at least one feed")
    return feeds


def _collect_feeds(parent, feeds, namespaces):
    for outline in parent.findall("outline", namespaces):
        if "xmlUrl" in outline.attrib:
            name, url = outline.get("text", ""), outline.get("xmlUrl")
            if not name.strip():
                raise ValueError("feed outline text must be a non-empty string")
            if not url.strip():
                raise ValueError("feed outline xmlUrl must be a non-empty string")
            feeds.append({"name": name, "url": url})
        _collect_feeds(outline, feeds, namespaces)


class FeedError(Exception):
    pass


def collect_feeds(feeds, *, item_limit=None, max_age_days=None, now=None, progress=True, feed_parser=None):
    if not isinstance(feeds, list) or not feeds:
        raise ValueError("feeds must be a non-empty array")
    for index, feed in enumerate(feeds):
        if not isinstance(feed, dict):
            raise ValueError(f"feeds[{index}] must be an object")
        for key in ("name", "url"):
            if not isinstance(feed.get(key), str) or not feed[key].strip():
                raise ValueError(f"feeds[{index}].{key} must be a non-empty string")
    if feed_parser is None:
        feed_parser = feedparser
    if not callable(getattr(feed_parser, "parse", None)):
        raise ValueError("feed_parser must respond to parse")
    if item_limit is not None and (type(item_limit) is not int or item_limit <= 0):
        raise ValueError("item_limit must be a positive integer")
    if max_age_days is not None and (type(max_age_days) is not int or max_age_days < 0):
        raise ValueError("max_age_days must be a non-negative integer")
    now = (now or datetime.now(UTC)).astimezone(UTC)
    result = {"feeds": [], "errors": []}
    for feed in feeds:
        if progress:
            print(f"Fetching: {feed['name']}", file=sys.stderr)
        try:
            items = _parse_feed(feed["url"], feed_parser)
            if max_age_days is not None:
                # Subtract datetimes instead of days from now to support arbitrarily large limits.
                items = [item for item in items
                         if (now - datetime.fromisoformat(item["published"])).total_seconds() <= max_age_days * 86_400]
            if item_limit is not None:
                items = items[:item_limit]
            result["feeds"].append({**feed, "items": items})
        except FeedError as error:
            result["errors"].append({**feed, "error": str(error)})
    return result


def _parse_feed(url, feed_parser):
    try:
        parsed = feed_parser.parse(url)
    except (URLError, OSError, ValueError, http.client.HTTPException) as error:
        raise FeedError(f"fetch error: {error}") from error
    status = parsed.get("status", 200)
    if status >= 400:
        reason = http.client.responses.get(status, "HTTP error")
        raise FeedError(f"fetch error: {status} {reason}")
    if parsed.bozo:
        error = parsed.bozo_exception
        if isinstance(error, (URLError, OSError, http.client.HTTPException)):
            raise FeedError(f"fetch error: {error}") from error
        raise FeedError(f"invalid feed: {parsed.bozo_exception}")
    if not parsed.version.startswith(("rss", "atom")):
        raise FeedError("unsupported feed format (expected RSS or Atom)")
    items = []
    for entry in parsed.entries:
        date = entry.get("published_parsed")
        if date is None and "updated_parsed" in entry:
            date = entry["updated_parsed"]
        if date is None:
            continue
        try:
            published = datetime.fromtimestamp(timegm(date), UTC)
        except (ValueError, OverflowError, OSError):
            continue
        summary = entry.get("summary")
        if summary is None:
            summary = next(iter(entry.get("content", [])), {}).get("value", "")
        items.append(_normalized_item(entry.get("title", ""), entry.get("link", ""),
                                      published, summary))
    return items


def _normalized_item(title, link, published, summary):
    return {"title": (title or "").strip(), "link": (link or "").strip(),
            "published": published.isoformat(timespec="seconds") if published else "",
            "summary": (summary or "").strip()[:SUMMARY_MAX_LENGTH]}


def main(arguments=None):
    parser = argparse.ArgumentParser(
        description="Fetch RSS 1.0, RSS 2.0, and Atom feeds configured in OPML 2.0.")
    parser.add_argument("--item-limit", type=int, metavar="INTEGER",
                        help="Maximum number of articles per feed (positive integer)")
    parser.add_argument("--max-age-days", type=int, metavar="INTEGER",
                        help="Maximum article age in days (non-negative integer)")
    parser.add_argument("config_path", metavar="CONFIG_PATH", help="Path to the OPML feed configuration")
    args = parser.parse_args(arguments)
    if args.item_limit is not None and args.item_limit <= 0:
        parser.error("--item-limit must be a positive integer")
    if args.max_age_days is not None and args.max_age_days < 0:
        parser.error("--max-age-days must be a non-negative integer")
    config_path = args.config_path
    try:
        feeds = load_opml(config_path)
    except (ValueError, OSError, UnicodeError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    item_limit = args.item_limit
    max_age_days = args.max_age_days
    print(f"Start: config={config_path} feeds={len(feeds)} "
          f"item_limit={item_limit if item_limit is not None else 'unlimited'} "
          f"max_age_days={max_age_days if max_age_days is not None else 'unlimited'}", file=sys.stderr)
    result = collect_feeds(feeds, item_limit=item_limit, max_age_days=max_age_days)
    print(f"Complete: articles={sum(len(feed['items']) for feed in result['feeds'])}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
