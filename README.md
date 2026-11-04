# feed-buster

The `summarize-feeds` Agent Skill fetches RSS 1.0, RSS 2.0, and Atom feeds as category-grouped JSON.
Choose the display format, language, and summary detail at invocation time.

Requires Python 3.12+, uv, and internet access. uv installs feedparser automatically.

## Installation

Use either command:

```sh
gh skill install takeyaqa/feed-buster
# or
npx skills add takeyaqa/feed-buster
```

## Usage

```text
Fetch all categories and show Japanese highlights and all articles grouped by category.
Fetch Example with up to 5 articles per feed from the last 3 days and return raw JSON.
Fetch all categories and prepare a three-minute Japanese narration.
```

Display instructions can also be included in scheduled tasks. Without them, the skill reports counts per category.
Interactive UI and audio depend on the host; a narration script does not start playback.

## Feed Configuration

Add an OPML 2.0 file to `skills/summarize-feeds/assets/`:

```xml
<opml version="2.0">
  <body>
    <outline text="Example" xmlUrl="https://example.com/feed.xml" />
  </body>
</opml>
```

At least one feed with non-empty `text` and `xmlUrl` is required. Nested outlines are supported.
Register the file in `assets/index.yaml`; each catalog entry is a category:

```yaml
configs:
  - name: Example
    file: example.feeds.opml
    description: Example feeds.
```

## CLI and Output

```sh
uv run skills/summarize-feeds/scripts/rss_fetch.py --category "Example" \
  --item-limit 5 --max-age-days 3 skills/summarize-feeds/assets/example.feeds.opml
```

`--category` returns `{"categories": [{"name": "Example", "config": "...", "feeds": [...], "errors": [...]}]}`.
Omitting it preserves the legacy `{"feeds": [...], "errors": [...]}` format. The skill runs once per selected
configuration and combines categories; the script does not read the YAML catalog.

- Feed: `name`, `url`, `items`. Article: `title`, `link`, `published`, `summary`.
- Error: `name`, `url`, `error`. Failed and empty categories are retained.
- Dates are UTC ISO 8601, with updated dates as fallback; undated articles are excluded.
- Excerpts may contain HTML and are limited to 1,000 characters. They are not AI summaries.
- Order and duplicates are preserved. Age filtering precedes the item limit; articles are not sorted.
- Stdout is JSON; stderr contains progress and diagnostics. Exit codes: `0` success, `1` feed failures with JSON,
  `2` invalid arguments or configuration without JSON. The script sets no request timeout.

See [SKILL.md](skills/summarize-feeds/SKILL.md) for validation and presentation rules.
