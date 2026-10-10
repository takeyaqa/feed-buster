---
name: summarize-feeds
description: Fetch RSS and Atom feeds with the bundled scripts/rss_fetch.py and OPML 2.0 feed configuration files in assets, then summarize highlights and all articles from the resulting JSON in the user's language. Use when asked to fetch or summarize configured feeds, recent articles, article lists, or RSS digests. Do not use for general web searches, arbitrary URL research, or inspecting the full text behind article links.
compatibility: Requires uv, Python 3.12 or later, and internet access. uv installs feedparser from PEP 723 script metadata automatically.
---

# Fetch and Summarize Feeds

Select the OPML feed configuration from the YAML catalog at `assets/index.yaml` that matches the user's instructions,
then run the configured feed-fetching script. Create a digest in the user's language using only the resulting JSON as
evidence.

## Fetch

1. Use `uv run --script` and `scripts/rss_fetch.py` as the fetching script. If it does not exist, report the problem and stop.
2. Read `assets/index.yaml`. If it does not exist, cannot be parsed as YAML, or its `configs` value is not an array,
   report the problem and stop.
3. Compare the user's instructions with the `name` and `description` of each `configs` entry, and select the configuration
   that best matches the intended purpose. If the user explicitly specifies a `file` or configuration file, select the
   matching entry. If no candidate matches or multiple candidates cannot be narrowed down to one, show the candidates'
   `name` and `description` values and ask the user to choose.
4. Resolve the selected entry's OPML `file` relative to the directory containing `assets/index.yaml`, and confirm that the
   file exists. If it does not, report the problem and stop.
5. Pass the selected OPML file as an argument, using absolute paths for both the fetching script and configuration file.
   If the user explicitly specifies a per-feed article limit or maximum article age, pass it with `--item-limit` or
   `--max-age-days`, respectively. Omit either option when the user does not specify it; do not infer defaults from the
   configuration file.

   ```sh
   uv run --script scripts/rss_fetch.py [--item-limit INTEGER] [--max-age-days INTEGER] <opml-file>
   ```

6. Preserve standard output, standard error, and the exit code. Do not save fetched results or summaries to files in the
   workspace.
7. If the sandbox blocks network access, request network permission limited to fetching the feeds. Do not switch to another
   fetching method.

## Evaluate the Result

- For exit code `0`, parse the JSON from standard output and summarize it normally.
- For exit code `1`, parse the JSON from standard output, summarize the successful results, and include the contents of
  `errors` at the end.
- For exit code `2`, a command that cannot be executed, or output that cannot be parsed as JSON, report standard error or
  the parsing error and stop. Do not generate a summary.
- Also stop and treat the result as invalid if the JSON root is not an object or if `feeds` and `errors` are not arrays.

## Summarize

1. Choose the summary language in the following priority order:
   1. Use the language explicitly specified by the user.
   2. If none is specified, use the language used primarily in the current conversation.
   3. If the conversation language cannot be determined, use English.
   4. Do not change the summary language based on the language of the source or article.
2. Flatten all `items` from every element in `feeds`, attaching the source `name` to each item. Do not deduplicate articles.
3. The fetching script excludes articles without a publication date. Interpret each `published` value as a UTC datetime
   and sort articles from newest to oldest, preserving fetch order for identical datetimes.
4. Use only `title`, `summary`, source, `published`, and `link` as evidence. Do not open article links, perform additional
   web searches, or add facts that are absent from the fetched result.
5. Preserve article titles and proper nouns in their original form, and write only each article's description as one or
   two sentences in the selected language. If `summary` is empty, do not infer content from the title; state in the selected
   language that the fetched result does not include a summary.
6. Identify three to five common trends or especially important topics across all articles. If there are no supporting articles,
   do not invent highlights; state in the selected language that there are no articles to summarize.

## Produce the Output

Use the following order, writing all headings and standard text in the selected language:

1. A result line showing the number of successful feeds, articles, and errors
2. A highlights heading
3. An article list heading
4. A fetch errors heading, included only when `errors` contains at least one entry

Format each entry in the article list as follows:

- With a link: `[original title](URL) — source — YYYY-MM-DD`
- Without a link: `original title — source — YYYY-MM-DD`
- For the publication date, use only the date portion of `published`; do not display the time or time zone.
- Use the selected language when displaying an empty title.
- After the heading line, add a one- or two-sentence summary in the selected language.

For fetch errors, show each `errors` entry's source name, URL, and error message unchanged.
