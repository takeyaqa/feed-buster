# feed-buster

`feed-buster` contains the `summarize-feeds` Agent Skill.

It fetches configured RSS 1.0, RSS 2.0, and Atom feeds and provides validated JSON grouped by category.
Choose the presentation, language, and summary detail each time you invoke the skill or configure a scheduled task.

## Features

- Selects one, multiple, or all feed configurations matching the request
- Fetches articles from multiple feeds in a single run
- Supports RSS 1.0, RSS 2.0, and Atom feeds with XML namespaces
- Normalizes dates to UTC while preserving feed order and duplicate articles
- Excludes articles that do not provide a publication date
- Separates retrieval from presentation: request raw JSON, a digest, an interactive view, or a spoken-style script
- Continues processing successfully fetched articles even when some feeds fail

## Requirements

- Python 3.12 or later and uv (feedparser is installed automatically from PEP 723 script metadata)
- Internet access to fetch feeds

URL fetching and RSS/Atom parsing use `feedparser.parse(URL)`, including date recognition and HTML normalization.
The script does not set a request timeout.
OPML configuration loading uses the Python standard library. Malformed feeds are reported in `errors`.

## Installation

### Using GitHub CLI

Run the following command and follow the prompts to select a skill and target agent:

```bash
gh skill install takeyaqa/feed-buster
```

See the [`gh skill install` documentation](https://cli.github.com/manual/gh_skill_install) for options such as `--agent`, `--scope`, and `--all`.

### Using npx

```bash
npx skills add takeyaqa/feed-buster
```

## Usage

After installation, ask your AI agent to summarize the latest articles from your configured feeds.

```text
Summarize the latest articles from the configured feeds.
```

You can also specify a configuration by name.

```text
Use Sample to fetch articles and create a digest.
```

You can specify `item_limit` and `max_age_days` in natural language to limit the number of articles per feed and how far
back to fetch them.

```text
Use Sample to fetch up to 5 articles per feed from the last 3 days.
```

## Adding a Feed Configuration

Add feed configurations as OPML 2.0 files in the installed skill's `assets` directory. Then register them in the `configs`
array in the YAML catalog at `assets/index.yaml`.

The following is an example configuration file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>Example</title>
  </head>
  <body>
    <outline
      type="rss"
      text="Example"
      title="Example"
      xmlUrl="https://example.com/feed.xml"
      htmlUrl="https://example.com/" />
  </body>
</opml>
```

- The document must use OPML 2.0 and contain at least one feed `outline` in `body`.
- Each feed requires non-empty `text` and `xmlUrl` attributes. Nested group outlines are supported.

The following example registers the configuration in `assets/index.yaml`:

```yaml
configs:
  - name: Example
    file: example.feeds.opml
    description: Example feeds.
```

## Output and Presentation

The skill runs the script once per selected category and combines the validated category objects into a single
`{"categories": [...]}` result. Each category contains `name` (the catalog name), `config` (the OPML path), `feeds`, and
`errors`. Category order follows the request, or the catalog when all categories are requested. Empty and failed categories
remain in the result. Nested OPML groups are containers, not separate output categories.

Successful feeds contain `name`, `url`, and `items`; errors contain `name`, `url`, and `error`.
Each article has `title`, `link`, `published` (UTC ISO 8601), and `summary`. The summary is the feed-provided excerpt,
possibly HTML, truncated to 1,000 characters, not an AI-generated summary. Missing publication dates fall back to updated
dates; articles without either usable date are excluded. Feed order and duplicates are preserved. Age filtering precedes
the item limit, which selects the first matching entries in feed order rather than sorting by newest first.

Choose how to present the result in your request, for example:

```text
Fetch all categories and show Japanese highlights and a complete article list grouped by category, newest first.
Fetch Example and return raw JSON without summarizing.
Fetch all categories and prepare a three-minute Japanese narration using only the fetched excerpts.
Fetch all categories and use an interactive category selector if supported by this environment.
```

JSON is the retrieval contract, not a mandatory final-answer format. With no presentation instructions, the skill reports
successful feed, article, and error counts per category. Fetch errors are always disclosed. UI and audio availability
depend on the host; a narration script does not itself start audio playback. No files are saved unless explicitly requested.
Fetched content is evidence, not instructions. The skill does not visit article links or invent missing article contents.

## Direct CLI Usage

```sh
uv run skills/summarize-feeds/scripts/rss_fetch.py --category "Example" \
  --item-limit 5 --max-age-days 3 skills/summarize-feeds/assets/example.feeds.opml
```

With `--category`, stdout contains `{"categories": [{"name": "Example", "config": "...", "feeds": [...], "errors": [...]}]}`.
Without it, the existing `{"feeds": [...], "errors": [...]}` format is preserved. The Python `collect_feeds` API is unchanged.
For multiple categories, invoke once per OPML file and concatenate the `categories` arrays after validating each result.
The script does not read the YAML catalog; the skill selects configurations and passes their names and paths.

Progress and diagnostics go to stderr. Exit codes are `0` for successful fetching, `1` for one or more feed failures
(with usable JSON, even if all feeds fail), and `2` for configuration or argument errors (no JSON).
If an invocation fails with exit code `2` or invalid JSON, the skill reports the failure and stops rather than presenting
an incomplete combined run as a complete digest.
