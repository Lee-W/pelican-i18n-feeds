# pelican-i18n-feeds

**pelican-i18n-feeds** is a Pelican plugin for multilingual sites built with [i18n_subsites](https://github.com/pelican-plugins/i18n-subsites). It writes Atom feeds that list the articles of **every** language — including articles that only exist in a subsite language — and gives you a helper that wires one feed per language into your `publishconf.py`.

## Why

With `i18n_subsites`, each language is built as its own site, and every article in a subsite language is removed from the main site. Pelican's feeds follow that:

- the main site's `FEED_ALL_ATOM` lists the main-language articles plus their translations, so an article written only in Japanese (no Chinese original) is missing;
- each subsite's feeds only hold that subsite's language;
- Pelican derives `FEED_DOMAIN` from the main `SITEURL` before the subsite exists, so a subsite's feed links and Atom self links miss its `/<lang>/` prefix unless you fix it per subsite;
- all feeds of one site share one Atom `<id>` (the site URL).

## Features

- `FEED_ALL_LANGUAGES_ATOM` / `CATEGORY_FEED_ALL_LANGUAGES_ATOM`: a site feed and per-category feeds with the published articles of every language, each article once, in Pelican's `FEED_ALL_ATOM` order, limited by `FEED_MAX_ITEMS`
- Only the main site writes them; subsites are detected automatically
- Optional per-feed Atom `<id>` (`I18N_FEEDS_URL_AS_ID`), with path prefixes that keep Pelican's id for existing subscribers
- `feed_settings()` helper: one call returns the feed settings of the main site and of every subsite (any number of languages), including `FEED_DOMAIN` fixes, `<head>` link titles for [attila](https://github.com/arulrajnet/attila) >= 3.5.0, and the per-language RSS link of `SOCIAL`
- A build warning when `I18N_UNTRANSLATED_ARTICLES` would make subsite-only articles disappear

## How it works

```text
content/ (zh-tw, ja, en articles)
   │
   ├─ main site (zh-tw) ── zh-tw/feeds/all.atom.xml        FEED_ATOM: zh-tw only
   │                    └─ feeds/all.atom.xml               FEED_ALL_LANGUAGES_ATOM: every language
   ├─ ja subsite ──────── ja/feeds/all.atom.xml             FEED_ATOM: ja only
   └─ en subsite ──────── en/feeds/all.atom.xml             FEED_ATOM: en only
```

The main site still reads every article; `i18n_subsites` only takes the other-language ones out of its lists and, before any site writes a file, points them at their subsite URL. This plugin collects them back from the main site's `generated_content` when it writes the all-language feeds. See [how it works](docs/how-it-works.md) for the details and the assumptions it makes about `i18n_subsites`.

## Installation

```bash
pip install pelican-i18n-feeds
```

It depends on `pelican>=4.7` and `pelican-i18n-subsites>=0.9.0`.

## Setup

### 1. Add to pelicanconf.py

Both plugins must be listed; their order does not matter (they hook different signals):

```python
PLUGINS = ["pelican.plugins.i18n_subsites", "pelican.plugins.i18n_feeds"]
I18N_UNTRANSLATED_ARTICLES = "remove"  # or "keep"; see Known limitations
```

With no feed settings (the usual development config), the plugin does nothing.

### 2. Wire the feeds in publishconf.py

Two languages (main `zh-tw`, subsite `ja`):

```python
from pelican.plugins.i18n_feeds import feed_settings
from pelicanconf import *  # noqa: F403
from pelicanconf import DEFAULT_LANG, I18N_SUBSITES, LANGUAGE_NAMES, SITENAME, SOCIAL

SITEURL = "https://example.com"
FEED_MAX_ITEMS = 30
globals().update(
    feed_settings(
        siteurl=SITEURL,
        sitename=SITENAME,
        default_lang=DEFAULT_LANG,
        subsites=I18N_SUBSITES,
        language_names=LANGUAGE_NAMES,  # {"zh-tw": "臺灣華語", "ja": "日本語"}
        all_languages_labels={
            "zh-tw": "全部語言 / All languages",
            "ja": "すべての言語 / All languages",
        },
        social=SOCIAL,
    )
)
# Each feed gets its own <id>, except the old feeds/ URLs subscribers hold.
I18N_FEEDS_URL_AS_ID = True
I18N_FEEDS_KEEP_ID_PREFIXES = ["feeds/"]
```

Three languages work the same way: put `en` in `I18N_SUBSITES` (and `LANGUAGE_NAMES`, optionally `all_languages_labels`) and the same call configures both subsites:

```python
I18N_SUBSITES = {"en": {"SITENAME": "My blog"}, "ja": {"SITENAME": "私のブログ"}}
LANGUAGE_NAMES = {"zh-tw": "臺灣華語", "en": "English", "ja": "日本語"}
```

Result (default paths):

| Feed | Contents |
| --- | --- |
| `feeds/all.atom.xml`, `feeds/{slug}.atom.xml` | every language |
| `zh-tw/feeds/all.atom.xml`, `zh-tw/feeds/{slug}.atom.xml` | main language |
| `en/feeds/...`, `ja/feeds/...` | that subsite's language |

Notes on `feed_settings()`:

- Call `globals().update(...)` **after** `from pelicanconf import *`: it replaces the module's `FEED_ALL_ATOM`, `FEED_ATOM`, `CATEGORY_FEED_ATOM`, `FEED_ALL_LANGUAGES_ATOM`, `CATEGORY_FEED_ALL_LANGUAGES_ATOM`, `FEED_LINK_TITLES`, `FEED_EXTRA_LINKS`, `I18N_FEEDS_URLS`, `I18N_FEEDS_ALL_LANGUAGES_URL`, `I18N_SUBSITES` and, with `social=`, `SOCIAL`. Set any of them again after the call to override it.
- In each subsite entry, it **replaces** the subsite's own `FEED_DOMAIN`, `FEED_ATOM`, `CATEGORY_FEED_ATOM`, `FEED_LINK_TITLES`, `FEED_EXTRA_LINKS` (and `SOCIAL` with `social=`): they are what the layout is made of. Change `I18N_SUBSITES[lang][...]` after the call if one subsite needs something else.
- It returns a new `I18N_SUBSITES` built from deep copies of your entries, so the result and the `I18N_SUBSITES` you passed in share no mutable objects.
- It raises `TypeError` when `subsites`, an entry of it, `language_names` or `all_languages_labels` is not a mapping, and `ValueError` when `default_lang` is also a subsite or a `SOCIAL` entry is not a `(name, link)` pair.
- You can also assign the keys you want one by one instead of `globals().update(...)`.

### Migrating from the entertainment-blog local plugin

The local `all_language_feeds` plugin always rewrote feed ids. Here that is opt-in, so to keep the same output set both:

```python
I18N_FEEDS_URL_AS_ID = True
I18N_FEEDS_KEEP_ID_PREFIXES = ["feeds/"]
```

## Configuration

Plugin settings (read at build time):

| Setting | Default | Description |
| --- | --- | --- |
| `FEED_ALL_LANGUAGES_ATOM` | `None` | Path of the all-language site feed, e.g. `"feeds/all.atom.xml"`. Unset: not written. |
| `FEED_ALL_LANGUAGES_ATOM_URL` | the path | URL of that feed, relative to `FEED_DOMAIN`, like Pelican's `FEED_ALL_ATOM_URL`. |
| `CATEGORY_FEED_ALL_LANGUAGES_ATOM` | `None` | Path of the all-language category feeds, with `{slug}`. |
| `CATEGORY_FEED_ALL_LANGUAGES_ATOM_URL` | the path | URL of those feeds, with `{slug}`. |
| `I18N_FEEDS_URL_AS_ID` | `False` | Use each feed's own URL as its Atom `<id>` (main site and subsites). Off: Pelican's id, the site URL, shared by all feeds of a site. |
| `I18N_FEEDS_KEEP_ID_PREFIXES` | `()` | With `I18N_FEEDS_URL_AS_ID`, feeds whose URL path (without the leading `/`) starts with one of these keep Pelican's id. A string is one prefix. Include your `SITEURL` path if the site is not at the domain root (`"blog/feeds/"`). |

The all-language feeds are written by the main site only: a site whose `DEFAULT_LANG` is a key of `I18N_SUBSITES` (how `i18n_subsites` builds subsites) is skipped, so subsites need no override.

`feed_settings()` arguments (keyword-only):

| Argument | Default | Description |
| --- | --- | --- |
| `siteurl` | required | Production `SITEURL` of the main site. |
| `sitename` | required | Main `SITENAME`; a subsite's own `SITENAME` override is used for its titles. |
| `default_lang` | required | Main `DEFAULT_LANG`. Must not be a subsite. |
| `subsites` | required | `I18N_SUBSITES`. A subsite `SITEURL` override is respected. |
| `language_names` | required | Language code → name used in titles; missing codes use the code. |
| `all_languages_labels` | `None` | Language code → label of the all-language link on that language's pages; default `"All languages"`. |
| `social` | `None` | Main `SOCIAL`. When given, the RSS entry of the main site and of every subsite (its own `SOCIAL`, or this one) points at that site's language feed. |
| `feed_path` | `"feeds/all.atom.xml"` | Site feed path, relative to each site root. |
| `category_feed_path` | `"feeds/{slug}.atom.xml"` | Category feed path. |
| `separator` | `" — "` | Joins the parts of a feed title. |
| `rss_names` | `("rss", "rss-square", "feed")` | `SOCIAL` names (case-insensitive) that are the RSS link; the default is the list attila shows as its RSS icon. |

It returns these settings for the main site, and the same per-site keys inside each `I18N_SUBSITES` entry:

| Key | Main site | Each subsite |
| --- | --- | --- |
| `FEED_ALL_ATOM` | `None` | (inherited) |
| `FEED_ATOM` / `CATEGORY_FEED_ATOM` | `<default_lang>/feed_path` / `<default_lang>/category_feed_path` | `feed_path` / `category_feed_path` |
| `FEED_ALL_LANGUAGES_ATOM` / `CATEGORY_FEED_ALL_LANGUAGES_ATOM` | `feed_path` / `category_feed_path` | (skipped on subsites) |
| `FEED_DOMAIN` | (Pelican default: `SITEURL`) | `SITEURL/<lang>` |
| `FEED_LINK_TITLES` | `{"FEED_ATOM": "<site> — <language>", "CATEGORY_FEED_ATOM": "<site> — <language> — {name}"}` | same, for the subsite |
| `FEED_EXTRA_LINKS` | `(("<site> — <label>", <all-language feed URL>),)` | same, for the subsite |
| `I18N_FEEDS_URLS` | `{lang: feed URL}` for every language | same |
| `I18N_FEEDS_ALL_LANGUAGES_URL` | all-language feed URL | same |
| `SOCIAL` | with `social=` only | with `social=` only |
| `I18N_SUBSITES` | new dict with the subsite keys merged | — |

## Theme integration

### attila >= 3.5.0

attila 3.5.0 reads `FEED_LINK_TITLES` (titles of the `<head>` feed links, keyed by setting name; category titles may use `{name}`) and `FEED_EXTRA_LINKS` (extra `<head>` links). With the helper, every page links its own language feed, its category feed on category pages, and the all-language feed. attila also shows the `SOCIAL` entry named `RSS` as the header RSS icon, which `social=` points at each language's feed.

attila < 3.5.0 ignores `FEED_LINK_TITLES` and `FEED_EXTRA_LINKS`: the links still point at the right feeds, with attila's default titles, and there is no `<head>` link to the all-language feed.

### Other themes

The plugin does not depend on any theme. Themes that render `FEED_DOMAIN` + `FEED_ATOM` (Pelican's `simple` theme does) get the per-language links; themes that only link `FEED_ALL_ATOM` (such as `notmyidea`) show no feed link, because the helper sets it to `None`. For an RSS icon outside `SOCIAL`, read the feed URL from `I18N_FEEDS_URLS[DEFAULT_LANG]` (or `I18N_FEEDS_ALL_LANGUAGES_URL`) in your templates.

## Known limitations

- **Atom only.** There are no RSS variants of the all-language feeds, and no all-language tag or author feeds.
- **Set `I18N_UNTRANSLATED_ARTICLES` to `"remove"` (or `"keep"`).** With `"hide"` or unset (`i18n_subsites` defaults to `"hide"`), `i18n_subsites` turns the main site's copy of each subsite-only article into a draft and the main site writes no page for it, so the all-language feeds leave those articles out (translations of main-site articles are still listed) and the plugin logs a warning. `"keep"` lists them with their main-site URL (`ARTICLE_LANG_URL`).
- **Relies on `i18n_subsites` internals.** It expects `i18n_subsites` to build the subsites from the main site's `get_writer` signal and to rewrite the removed articles' URLs before any site writes (true for 0.9.0 and 1.0.0). See [how it works](docs/how-it-works.md).
- **Feed `<id>` changes are opt-in.** Turning on `I18N_FEEDS_URL_AS_ID` changes the id of existing feeds not covered by `I18N_FEEDS_KEEP_ID_PREFIXES`; most readers key on the feed URL, but some may treat the feed as new.
- With three or more languages, an article translated into some but not all subsite languages makes Pelican warn about "2 original items" on the subsites lacking it. That is Pelican's translation grouping, not this plugin; mark the non-original versions with `Translation: true` to silence it.

## License

MIT © Wei Lee
