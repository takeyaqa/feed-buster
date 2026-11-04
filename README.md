# feed-buster

The `summarize-feeds` Agent Skill fetches RSS 1.0, RSS 2.0, and Atom feeds as JSON.
Choose the display format, language, and summary detail at invocation time.
Requires Python 3.12+, uv, and internet access; uv installs feedparser automatically.

## Installation

```sh
gh skill install takeyaqa/feed-buster
# or
npx skills add takeyaqa/feed-buster
```

## Usage

Requests without an explicit category fetch all feeds, including uncategorized ones. Category filters are opt-in.

```text
Fetch feeds and show Japanese highlights and all articles grouped by category.
Fetch News with up to 5 articles per feed from the last 3 days and return raw JSON.
Fetch all categories and prepare a three-minute Japanese narration.
```

Without display instructions, the skill reports counts per category. Interactive UI and audio depend on the host.

## Configuration

Manage all feeds in `skills/summarize-feeds/assets/feeds.opml`; no YAML catalog is needed.
Add a `category` attribute to each feed outline:

```xml
<opml version="2.0">
  <body>
    <outline text="News source" category="News" xmlUrl="https://example.com/news.xml" />
    <outline text="Security source" category="Security" xmlUrl="https://example.com/security.xml" />
  </body>
</opml>
```

At least one feed with non-empty `text` and `xmlUrl` is required. Categories are trimmed literal labels;
missing means uncategorized, while blank values are invalid. Nested outlines are supported without category inheritance.
To migrate, copy feed outlines from the old OPML files into this file and assign their former catalog names as categories.

## CLI and Output

```sh
uv run skills/summarize-feeds/scripts/rss_fetch.py \
  --category "News" --category "Security" --item-limit 5 --max-age-days 3 \
  skills/summarize-feeds/assets/feeds.opml
```

Omit `--category` to fetch all feeds, including uncategorized ones. Repeat it to select multiple exact labels.
Unknown categories fail before fetching. Selection preserves OPML order and does not duplicate feeds for repeated filters.

Output always has `feeds` and `errors` arrays. Each entry retains its `name`, `url`, and optional `category`, plus
`items` for success or `error` for failure. Articles contain `title`, `link`, `published`, and `summary`.

- Dates are UTC ISO 8601, with updated dates as fallback; undated articles are excluded.
- Excerpts may contain HTML and are limited to 1,000 characters. They are not AI summaries.
- Order and duplicates are preserved. Age filtering precedes the item limit; articles are not sorted.
- Stdout is JSON; stderr contains progress and diagnostics. Exit codes: `0` success, `1` feed failures with JSON,
  `2` invalid arguments or configuration without JSON. The script sets no request timeout.

See [SKILL.md](skills/summarize-feeds/SKILL.md) for validation and presentation rules.
