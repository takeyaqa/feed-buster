# Repository Guidelines

## Scope and Sources of Truth

- These instructions apply to the entire repository.
- Treat the checked-in files as authoritative. Keep `README.md`, `skills/summarize-feeds/SKILL.md`, the Python implementation,
  tests, and feed assets consistent when a change affects their shared behavior.
- Keep changes small and focused. Discuss new features or dependencies before introducing them; this project is primarily
  maintained by its author and generally accepts only small fixes.

## Project Layout

- `skills/summarize-feeds/SKILL.md`: agent-facing workflow and output contract.
- `skills/summarize-feeds/scripts/rss_fetch.py`: OPML loading, feed fetching and parsing, filtering, JSON output, and CLI
  handling.
- `skills/summarize-feeds/assets/index.yaml`: catalog of available feed configurations.
- `skills/summarize-feeds/assets/*.feeds.opml`: OPML 2.0 feed lists.
- `test/test_rss_fetch.py`: unittest coverage for the loader, parser, filters, error handling, and result schema.
- `mise.toml`: the required Python version.

## Environment and Commands

- Use Python 3.12 or later. `mise.toml` and the devcontainer select Python 3.12 for development.
- The script declares feedparser through PEP 723 inline metadata. Use uv to resolve and run it.
- Run the complete test suite:

  ```sh
  uv run --with feedparser -- python -m unittest discover -s test -v
  ```

- Check Python syntax:

  ```sh
  uv run -- python -m py_compile skills/summarize-feeds/scripts/rss_fetch.py test/test_rss_fetch.py
  ```

- Inspect the CLI without network access:

  ```sh
  uv run --script skills/summarize-feeds/scripts/rss_fetch.py --help
  ```

- A live fetch requires internet access:

  ```sh
  uv run --script skills/summarize-feeds/scripts/rss_fetch.py \
    [--item-limit INTEGER] [--max-age-days INTEGER] \
    skills/summarize-feeds/assets/example.feeds.opml
  ```

  Do not save fetched JSON or generated summaries in the repository unless explicitly requested.

## Python Conventions

- Follow PEP 8 with four-space indentation and standard Python naming.
- Preserve the minimal public API. `collect_feeds` is the intended public operation; prefix implementation helpers
  with `_`.
- Inject collaborators as objects with a `parse` method returning feedparser results. Collection tests should use deterministic fake parsers.
- Validate inputs at the boundary and keep error messages specific. Expected feed transport and parsing failures should
  be represented in the result; unexpected collaborator or programming errors should propagate.
- Avoid stateful per-run options. `item_limit`, `max_age_days`, `now`, and `progress` belong to `collect_feeds`.

## Testing and Verification

- Add or update unittest coverage for every behavior change. Prefer inline RSS/Atom/OPML fixtures and injected sequential
  parsers so tests remain fast and offline. HTTP/CLI tests use a loopback server; they require local socket access but no
  internet access.
- Cover success, boundary, and failure cases when changing validation, filtering, parsing, or CLI contracts.
- Before handing off a change, run the full test suite and the syntax check. Also inspect the relevant CLI path when
  command-line behavior changes.
