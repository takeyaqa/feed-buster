#!/usr/bin/env python3
"""Fetch OPML-configured RSS and Atom feeds using only the standard library."""

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import getopt
import html
import http.client
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from xml.dom import Node, minidom
from xml.parsers.expat import ExpatError

ATOM = "http://www.w3.org/2005/Atom"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RSS1 = "http://purl.org/rss/1.0/"
DC = "http://purl.org/dc/elements/1.1/"
CONTENT = "http://purl.org/rss/1.0/modules/content/"
UTC = timezone.utc


def _children(parent, name, namespace=None):
    if parent is None:
        return []
    return [child for child in parent.childNodes
            if child.nodeType == Node.ELEMENT_NODE and child.localName == name
            and child.namespaceURI == namespace]


def _child(parent, name, namespace=None):
    children = _children(parent, name, namespace)
    return children[-1] if children else None


def _text(element):
    if element is None:
        return None
    return "".join(child.data for child in element.childNodes
                   if child.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE))


def _strip(value):
    # Match the original script's String#strip, including its Unicode behavior.
    return "" if value is None else value.strip(" \t\r\n\v\f\0")


def _date(value):
    if not value:
        return None
    value = _strip(value)
    # Time accepts leap seconds and midnight written as 24:00:00.
    extra = timedelta()
    if re.search(r"[T ]24:00:00", value):
        value = re.sub(r"([T ])24:00:00", r"\g<1>00:00:00", value)
        extra += timedelta(days=1)
    if re.search(r":60(?=[.,Z+\- ]|$)", value):
        value = re.sub(r":60(?=[.,Z+\- ]|$)", ":59", value)
        extra += timedelta(seconds=1)
    for parser in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            result = parser(value.replace("Z", "+00:00") if parser == datetime.fromisoformat else value)
            result = result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)
            return result + extra
        except (ValueError, TypeError, OverflowError):
            continue
    return None


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


class FetchError(Exception):
    pass


@dataclass
class Result:
    feeds: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def has_errors(self):
        return bool(self.errors)

    def to_dict(self):
        return {"feeds": self.feeds, "errors": self.errors}


class HTTPFeedFetcher:
    def fetch(self, url):
        try:
            with urlopen(url, timeout=RSSFetch.FETCH_TIMEOUT_SECONDS) as response:
                return response.read()
        except HTTPError as error:
            raise FetchError(f"fetch error: {error.code} {error.reason}") from error
        except (URLError, OSError, ValueError, http.client.HTTPException) as error:
            reason = error.reason if isinstance(error, URLError) else error
            raise FetchError(f"fetch error: {reason}") from error


class RSSFetch:
    SUMMARY_MAX_LENGTH = 1_000
    FETCH_TIMEOUT_SECONDS = 10

    def __init__(self, *, feeds, feed_fetcher=None):
        if not isinstance(feeds, list) or not feeds:
            raise ValueError("feeds must be a non-empty array")
        for index, feed in enumerate(feeds):
            if not isinstance(feed, dict):
                raise ValueError(f"feeds[{index}] must be an object")
            for key in ("name", "url"):
                if not isinstance(feed.get(key), str) or not _strip(feed[key]):
                    raise ValueError(f"feeds[{index}].{key} must be a non-empty string")
        if feed_fetcher is None:
            feed_fetcher = HTTPFeedFetcher()
        if not callable(getattr(feed_fetcher, "fetch", None)):
            raise ValueError("feed_fetcher must respond to fetch")
        self._feeds = feeds
        self._feed_fetcher = feed_fetcher

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
                items = self._parse_feed(self._feed_fetcher.fetch(feed["url"]))
                if max_age_days is not None:
                    # Subtract datetimes instead of days from now to support arbitrarily large limits.
                    items = [item for item in items
                             if (now - _date(item["published"])).total_seconds() <= max_age_days * 86_400]
                if item_limit is not None:
                    items = items[:item_limit]
                result.feeds.append({**feed, "items": items})
            except (FeedError, FetchError) as error:
                result.errors.append({**feed, "error": str(error)})
        return result

    def _parse_feed(self, data):
        try:
            document = minidom.parseString(data)
        except (ExpatError, LookupError, UnicodeError) as error:
            raise FeedError(f"invalid XML: {error}") from error
        with document:
            root = document.documentElement
            if (root.namespaceURI, root.localName) == (ATOM, "feed"):
                items = [self._atom_item(entry) for entry in _children(root, "entry", ATOM)]
            elif (root.namespaceURI, root.localName) == (None, "rss"):
                items = self._rss_items(root, None)
            elif (root.namespaceURI, root.localName) == (RDF, "RDF"):
                items = self._rss_items(root, RSS1)
            else:
                raise FeedError("unsupported feed format (expected RSS or Atom)")
            return [item for item in items if item["published"]]

    def _rss_items(self, root, namespace):
        channel = _child(root, "channel", namespace)
        if channel is None:
            raise FeedError("invalid XML: required variables of maker.channel are not set: id, title")
        title = _text(_child(channel, "title", namespace))
        author = _text(_child(channel, "managingEditor", namespace)) or title
        if author is None:
            raise FeedError("invalid XML: required variables of maker.channel.author are not set: name")
        missing = []
        if _child(channel, "link", namespace) is None:
            missing.append("id")
        if title is None:
            missing.append("title")
        if missing:
            raise FeedError("invalid XML: required variables of maker.channel are not set: " + ", ".join(missing))
        items = []
        parent = root if namespace == RSS1 else channel
        for entry in _children(parent, "item", namespace):
            published = (_date(_text(_child(entry, "date", DC))) if namespace == RSS1
                         else _date(_text(_child(entry, "pubDate"))))
            if published is None:
                continue
            title = _text(_child(entry, "title", namespace))
            if title is None:
                raise FeedError("invalid XML: required variables of maker.item are not set: title")
            summary = _text(_child(entry, "description", namespace))
            if summary is None:
                summary = _text(_child(entry, "encoded", CONTENT))
            items.append(self._normalized_item(title, _text(_child(entry, "link", namespace)), published, summary))
        return items

    def _atom_item(self, entry):
        summary = self._atom_text(_child(entry, "summary", ATOM))
        if summary is None:
            summary = self._atom_text(_child(entry, "content", ATOM))
        links = [link for link in _children(entry, "link", ATOM) if _strip(link.getAttribute("href"))]
        selected = next((link for link in links
                         if not link.hasAttribute("rel") or link.getAttribute("rel") == "alternate"),
                        next(iter(links), None))
        published = (_date(_text(_child(entry, "published", ATOM)))
                     or _date(_text(_child(entry, "updated", ATOM))))
        return self._normalized_item(self._atom_text(_child(entry, "title", ATOM)),
                                     selected.getAttribute("href") if selected is not None else "",
                                     published, summary)

    def _atom_text(self, element):
        if element is None:
            return None
        kind = element.getAttribute("type")
        if element.localName == "content" and element.hasAttribute("src"):
            return ""
        if kind == "xhtml":
            nodes = [node for node in element.childNodes if node.nodeType == Node.ELEMENT_NODE]
            if not nodes:
                return ""
            return self._xml_text(nodes[0], include_namespaces=True)
        if element.localName == "content" and (kind.endswith("/xml") or kind.endswith("+xml")):
            return "".join(self._xml_text(node, include_namespaces=True) for node in element.childNodes)
        value = _text(element)
        if element.localName == "content" and kind not in ("", "text", "html") and not kind.startswith("text/"):
            value = base64.b64decode(value).decode("utf-8")
        return value

    def _xml_text(self, node, include_namespaces=False):
        # RSS's XML content preserves markup and decoded character data.
        if node.nodeType in (Node.TEXT_NODE, Node.CDATA_SECTION_NODE):
            return node.data
        if node.nodeType != Node.ELEMENT_NODE:
            return ""
        attributes = dict(node.attributes.items())
        if include_namespaces:
            ancestors = []
            parent = node.parentNode
            while parent is not None and parent.nodeType == Node.ELEMENT_NODE:
                ancestors.append(parent)
                parent = parent.parentNode
            namespaces = {}
            for parent in reversed(ancestors):
                namespaces.update((key, value) for key, value in parent.attributes.items()
                                  if key == "xmlns" or key.startswith("xmlns:"))
            for key, value in namespaces.items():
                attributes.setdefault(key, value)
        attributes = "".join(f' {key}="{html.escape(value, quote=True).replace("&#x27;", "&#39;")}"'
                             for key, value in attributes.items())
        children = "".join(self._xml_text(child) for child in node.childNodes)
        if not node.childNodes:
            return f"<{node.tagName}{attributes}/>"
        return f"<{node.tagName}{attributes}>{children}</{node.tagName}>"

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
