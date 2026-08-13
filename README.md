# feed-buster

`feed-buster` contains the `summarize-feeds` Agent Skill.

It fetches configured RSS 1.0, RSS 2.0, and Atom feeds and presents highlights and a complete article list in the
user's language.

It collects recent articles from multiple feeds and creates a digest in the language specified by the user or used
primarily in the conversation.

## Features

- Selects the feed configuration that best matches the request
- Fetches articles from multiple feeds in a single run
- Supports RSS 1.0, RSS 2.0, and Atom feeds with XML namespaces
- Normalizes publication dates and displays the newest articles first
- Excludes articles that do not provide a publication date
- Summarizes the results in the user's language, organized as highlights, an article list, and fetch errors
- Continues processing successfully fetched articles even when some feeds fail

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

## Output

The Skill produces a digest in the following format. For headings and standard text, it first uses the language specified
by the user, then the language used primarily in the current conversation. If the conversation language cannot be determined,
it uses English.

1. Number of successful feeds, articles, and errors
2. Highlights
3. Article list
4. Fetch errors (only when errors occur)

Article titles and proper nouns are preserved in their original form, while descriptions are written in the selected language.
If an article summary is unavailable, the Skill does not infer its contents from the title. The language of the source or
article does not change the digest language.
