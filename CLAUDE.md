# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

All tasks run via `uv` + `poe` (poethepoet). Tasks are defined in `pyproject.toml` under `[tool.poe.tasks]`.

```bash
uv run poe format         # ruff check --fix && ruff format
uv run poe lint           # ruff check && mypy
uv run poe test           # pytest -n auto --dist=loadfile
uv run poe cover          # test + coverage report
uv run poe check-commit   # commitizen check on commits since origin/main
uv run poe all            # format → lint → check-commit → cover
uv run poe ci             # check-commit → prek run --all-files → cover
uv run poe setup-pre-commit  # install pre-commit hooks via prek
```

Single test: `uv run pytest tests/test_i18n_feeds.py::test_name`. Tests run in parallel with `--dist=loadfile`, so file-level fixtures stay on the same worker.

Releases: `cz bump` updates the version in `pyproject.toml` and regenerates `CHANGELOG.md` from conventional-commit history. Don't hand-edit `CHANGELOG.md` — it's regenerated.

## Architecture

The plugin is a single-file implementation: `src/pelican/plugins/i18n_feeds/i18n_feeds.py`. See `docs/how-it-works.md` for the `i18n_subsites` build order it relies on.

### Signal flow

`register()` connects two Pelican signals:

1. `signals.article_writer_finalized` → `write_feeds`: on the main site only (`is_subsite` is false), collects `all_language_articles` and writes `FEED_ALL_LANGUAGES_ATOM` and `CATEGORY_FEED_ALL_LANGUAGES_ATOM`. Warns when `I18N_UNTRANSLATED_ARTICLES` is `"hide"`.
2. `signals.feed_generated` → `use_feed_url_as_id`: when `I18N_FEEDS_URL_AS_ID` is on, replaces each feed's `<id>` with its URL unless the URL path starts with one of `I18N_FEEDS_KEEP_ID_PREFIXES`. Runs for every feed of every site, Pelican's own included.

### Dependence on i18n_subsites internals

`all_language_articles` reads the main site's `context["generated_content"]` to find the articles `i18n_subsites` removed. It works because `i18n_subsites` rewrites their URLs (`override_url`) for all generators before any site writes. If an `i18n_subsites` upgrade changes that order, the subsite-only entries in `feeds/` would link to the main site: `test_three_languages_split_feeds_with_every_article_in_feeds` catches it.

### `feed_settings()` helper

A pure function used from `publishconf.py`: it returns the main site's feed settings plus a new `I18N_SUBSITES` with each subsite's `FEED_DOMAIN`, `FEED_ATOM`, `CATEGORY_FEED_ATOM`, `FEED_LINK_TITLES`, `FEED_EXTRA_LINKS` (attila >= 3.5.0 shape) and optional `SOCIAL`. It must not import any theme and must not modify its inputs.

## Tests

`tests/test_i18n_feeds.py` builds real three-language sites (zh-tw main, ja and en subsites) with Pelican's `simple` theme in a **subprocess**: `i18n_subsites` keeps module state and Pelican signals stay connected within one process. The subprocess sets up logging with level names, and every build asserts there is no `WARNING` unless the test expects one. Coverage only counts the in-process unit tests, so the reported percentage understates what the subprocess builds exercise.

## Conventions

- **Conventional commits** are required — `cz check` runs in pre-commit (and via `poe check-commit`). `cz bump` reads commit history to choose the version bump and write the changelog entry.
- **Type checking**: mypy runs on `src` and `tests` with `disallow_untyped_decorators`, `warn_return_any`, etc. The `pelican.*` modules are not typed, so missing imports are ignored for that namespace only.
- **Pre-commit**: `prek` (a faster pre-commit drop-in) is the runner. Hooks live in `.pre-commit-config.yaml` and include `commitizen`, `codespell`, `blacken-docs`, `taplo`, plus local `poe format` / `poe lint` entries.
