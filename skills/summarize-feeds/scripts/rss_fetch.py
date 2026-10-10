#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "feedparser",
# ]
# ///
"""Fetch OPML-configured RSS and Atom feeds with feedparser."""

from calendar import timegm
from dataclasses import dataclass, field
from datetime import datetime, timezone
import getopt
import http.client
import json
from pathlib import Path
import re
import sys
from urllib.error import URLError
from xml.dom import Node, minidom
from xml.parsers.expat import ExpatError

import feedparser

UTC = timezone.utc


def _children(parent, name, namespace=None):
    if parent is None:
        return []
    return [child for child in parent.childNodes
            if child.nodeType == Node.ELEMENT_NODE and child.localName == name
            and child.namespaceURI == namespace]


def _strip(value):
    # Match the original script's String#strip, including its Unicode behavior.
    return "" if value is None else value.strip(" \t\r\n\v\f\0")


class OPMLFeedLoader:
    @staticmethod
    def load(path):
        try:
            document = minidom.parseString(Path(path).read_text(encoding="utf-8"))
        except ExpatError as error:
            raise ValueError(f"invalid XML: {error}") from error
        with document:
            root = document.documentElement
            if root.localName != "opml":
                raise ValueError("document root must be opml")
            if root.getAttribute("version") != "2.0":
                raise ValueError("OPML version must be 2.0")
            body = next(iter(_children(root, "body", root.namespaceURI)), None)
            if body is None:
                raise ValueError("OPML body is required")
            feeds = []
            OPMLFeedLoader._collect(body, feeds)
            if not feeds:
                raise ValueError("OPML must contain at least one feed")
            return feeds

    @staticmethod
    def _collect(parent, feeds):
        for outline in _children(parent, "outline", parent.namespaceURI):
            if outline.hasAttribute("xmlUrl"):
                name, url = outline.getAttribute("text"), outline.getAttribute("xmlUrl")
                if not _strip(name):
                    raise ValueError("feed outline text must be a non-empty string")
                if not _strip(url):
                    raise ValueError("feed outline xmlUrl must be a non-empty string")
                feeds.append({"name": name, "url": url})
            OPMLFeedLoader._collect(outline, feeds)


class FeedError(Exception):
    pass


@dataclass
class Result:
    feeds: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def has_errors(self):
        return bool(self.errors)

    def to_dict(self):
        return {"feeds": self.feeds, "errors": self.errors}


class RSSFetch:
    SUMMARY_MAX_LENGTH = 1_000

    def __init__(self, *, feeds, feed_parser=None):
        if not isinstance(feeds, list) or not feeds:
            raise ValueError("feeds must be a non-empty array")
        for index, feed in enumerate(feeds):
            if not isinstance(feed, dict):
                raise ValueError(f"feeds[{index}] must be an object")
            for key in ("name", "url"):
                if not isinstance(feed.get(key), str) or not _strip(feed[key]):
                    raise ValueError(f"feeds[{index}].{key} must be a non-empty string")
        if feed_parser is None:
            feed_parser = feedparser
        if not callable(getattr(feed_parser, "parse", None)):
            raise ValueError("feed_parser must respond to parse")
        self._feeds = feeds
        self._feed_parser = feed_parser

    def collect_feeds(self, *, item_limit=None, max_age_days=None, now=None, progress=True):
        if item_limit is not None and (type(item_limit) is not int or item_limit <= 0):
            raise ValueError("item_limit must be a positive integer")
        if max_age_days is not None and (type(max_age_days) is not int or max_age_days < 0):
            raise ValueError("max_age_days must be a non-negative integer")
        now = (now or datetime.now(UTC)).astimezone(UTC)
        result = Result()
        for feed in self._feeds:
            if progress:
                print(f"Fetching: {feed['name']}", file=sys.stderr)
            try:
                items = self._parse_feed(feed["url"])
                if max_age_days is not None:
                    # Subtract datetimes instead of days from now to support arbitrarily large limits.
                    items = [item for item in items
                             if (now - datetime.fromisoformat(item["published"])).total_seconds() <= max_age_days * 86_400]
                if item_limit is not None:
                    items = items[:item_limit]
                result.feeds.append({**feed, "items": items})
            except FeedError as error:
                result.errors.append({**feed, "error": str(error)})
        return result

    def _parse_feed(self, url):
        try:
            parsed = self._feed_parser.parse(url)
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
            items.append(self._normalized_item(entry.get("title", ""), entry.get("link", ""),
                                               published, summary))
        return items

    def _normalized_item(self, title, link, published, summary):
        return {"title": _strip(title), "link": _strip(link),
                "published": published.isoformat(timespec="seconds") if published else "",
                "summary": _strip(summary)[:self.SUMMARY_MAX_LENGTH]}


HELP = """Usage: rss_fetch.py [--item-limit INTEGER] [--max-age-days INTEGER] CONFIG_PATH
Fetch RSS 1.0, RSS 2.0, and Atom feeds configured in OPML 2.0.
        --item-limit INTEGER         Maximum number of articles per feed (positive integer)
        --max-age-days INTEGER       Maximum article age in days (non-negative integer)
    -h, --help                       Show this help"""


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    runtime_options = {"item_limit": None, "max_age_days": None}
    try:
        try:
            options, paths = getopt.gnu_getopt(arguments, "h", ["help", "item-limit=", "max-age-days="])
        except getopt.GetoptError as error:
            option = ("--" if len(error.opt) > 1 else "-") + error.opt
            category = "missing argument" if "requires argument" in error.msg else "invalid option"
            raise ValueError(f"{category}: {option}") from error
        for option, value in options:
            if option in ("-h", "--help"):
                print(HELP)
                return 0
            # Keep OptionParser's decimal, legacy octal, hex and binary integer inputs.
            integer_pattern = r"[+-]?(?:0[xX][0-9a-fA-F](?:_?[0-9a-fA-F])*|0[bB][01](?:_?[01])*|[0-9](?:_?[0-9])*)"
            if not re.fullmatch(integer_pattern, value):
                raise ValueError(f"invalid argument: {option} {value}")
            digits = value.lstrip("+-").replace("_", "")
            base = 0 if digits.lower().startswith(("0x", "0b")) else (8 if digits.startswith("0") else 10)
            try:
                number = int(value, base)
            except ValueError as error:
                raise ValueError(f"invalid argument: {option} {value}") from error
            if option == "--item-limit" and number <= 0:
                raise ValueError("invalid argument: --item-limit --item-limit must be a positive integer")
            if option == "--max-age-days" and number < 0:
                raise ValueError("invalid argument: --max-age-days --max-age-days must be a non-negative integer")
            runtime_options[option[2:].replace("-", "_")] = number
        if len(paths) != 1:
            raise ValueError("missing argument: CONFIG_PATH")
    except ValueError as error:
        print(f"Argument error: {error}", file=sys.stderr)
        print(HELP, file=sys.stderr)
        return 2
    config_path = paths[0]
    try:
        feeds = OPMLFeedLoader.load(config_path)
        rss_fetch = RSSFetch(feeds=feeds)
    except (ValueError, OSError, UnicodeError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    item_limit = runtime_options["item_limit"]
    max_age_days = runtime_options["max_age_days"]
    print(f"Start: config={config_path} feeds={len(feeds)} "
          f"item_limit={item_limit if item_limit is not None else 'unlimited'} "
          f"max_age_days={max_age_days if max_age_days is not None else 'unlimited'}", file=sys.stderr)
    result = rss_fetch.collect_feeds(**runtime_options)
    print(f"Complete: articles={sum(len(feed['items']) for feed in result.feeds)}", file=sys.stderr)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 1 if result.has_errors() else 0


if __name__ == "__main__":
    sys.exit(main())
