# Repository Guidelines

## Scope and Sources of Truth

- These instructions apply to the entire repository.
- Treat the checked-in files as authoritative. Keep `README.md`, `skills/summarize-feeds/SKILL.md`, the Ruby implementation,
  tests, and feed assets consistent when a change affects their shared behavior.
- Keep changes small and focused. Discuss new features or dependencies before introducing them; this project is primarily
  maintained by its author and generally accepts only small fixes.

## Project Layout

- `skills/summarize-feeds/SKILL.md`: agent-facing workflow and output contract.
- `skills/summarize-feeds/scripts/rss_fetch.rb`: OPML loading, feed fetching and parsing, filtering, JSON output, and CLI
  handling.
- `skills/summarize-feeds/assets/index.yaml`: catalog of available feed configurations.
- `skills/summarize-feeds/assets/*.feeds.opml`: OPML 2.0 feed lists.
- `test/rss_fetch_test.rb`: Minitest coverage for the loader, parser, filters, error handling, and result schema.
- `mise.toml`: the required Ruby version.

## Environment and Commands

- Use the repository Ruby through mise, not the system Ruby.
- The implementation currently uses Ruby standard-library dependencies only. Do not add a gem or another toolchain without
  approval.
- Run the complete test suite:

  ```sh
  mise exec -- ruby -Itest test/rss_fetch_test.rb
  ```

- Check Ruby syntax:

  ```sh
  mise exec -- ruby -c skills/summarize-feeds/scripts/rss_fetch.rb
  ```

- Inspect the CLI without network access:

  ```sh
  mise exec -- ruby skills/summarize-feeds/scripts/rss_fetch.rb --help
  ```

- A live fetch requires internet access:

  ```sh
  mise exec -- ruby skills/summarize-feeds/scripts/rss_fetch.rb \
    [--item-limit INTEGER] [--max-age-days INTEGER] \
    skills/summarize-feeds/assets/example.feeds.opml
  ```

  Do not save fetched JSON or generated summaries in the repository unless explicitly requested.

## Ruby Conventions

- Follow the existing style: `# frozen_string_literal: true`, two-space indentation, double-quoted strings, and standard
  Ruby naming.
- Preserve the minimal public API. `RSSFetch#collect_feeds` is the intended public operation; keep implementation helpers
  below `private`.
- Inject collaborators as objects that respond to `fetch`. Tests should use deterministic fake fetchers rather than network
  calls or method stubs.
- Validate inputs at the boundary and keep error messages specific. Expected feed transport and parsing failures should
  be represented in the result; unexpected collaborator or programming errors should propagate.
- Avoid stateful per-run options. `item_limit`, `max_age_days`, `now`, and `progress` belong to `collect_feeds`.

## Testing and Verification

- Add or update Minitest coverage for every behavior change. Prefer inline RSS/Atom/OPML fixtures and injected sequential
  fetchers so tests remain fast and offline.
- Cover success, boundary, and failure cases when changing validation, filtering, parsing, or CLI contracts.
- Before handing off a change, run the full test suite and the syntax check. Also inspect the relevant CLI path when
  command-line behavior changes.
