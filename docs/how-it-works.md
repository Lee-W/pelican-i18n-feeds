# How it works

This page explains what the plugin relies on, so you can judge whether an
`i18n_subsites` or Pelican upgrade may affect it.

## Build order with i18n_subsites

`i18n_subsites` (0.9.0 and 1.0.0) builds a multilingual site like this:

1. The main site reads every article. On `article_generator_pretaxonomy`,
   `i18n_subsites` removes the articles and translations in a subsite
   language from the main site's lists, and remembers them per generator.
2. On the main site's `get_writer` signal it builds the next subsite, whose
   own `get_writer` builds the next one, and so on.
3. When the queue is empty, it rewrites the URLs of every remembered article
   (`override_url`) to point at its subsite, and interlinks translations,
   for **all** generators — before any site writes a file.
4. The sites then write their output: the last subsite first, the main site
   last.

The main site's `context["generated_content"]` still holds every article it
read, including the removed ones. By step 4 those objects link to their
subsite, so the main site can put them in its feeds without sharing any
state with the subsite builds.

## Collecting the articles

`all_language_articles(generator)` returns, once per source file:

1. the main site's articles,
2. their translations (Pelican's `FEED_ALL_ATOM` order),
3. the published `Article` objects of `generated_content` — the ones only a
   subsite publishes — except those whose source path is in the generator's
   drafts (see `"hide"` below), sorted by source path, because files are
   read in no fixed order and same-date articles keep the order they come in,

then orders them with `ARTICLE_ORDER_BY`. Drafts, hidden articles and pages
are never included. Pelican's writer cuts each feed at `FEED_MAX_ITEMS`.

## Main site only

i18n_subsites builds each subsite from a copy of the main settings with
`DEFAULT_LANG` set to the subsite language. The plugin writes the
all-language feeds only when `DEFAULT_LANG` is not a key of `I18N_SUBSITES`,
so the inherited `FEED_ALL_LANGUAGES_ATOM` does not make every subsite write
another copy.

## `I18N_UNTRANSLATED_ARTICLES`

| Value | Effect on the all-language feeds |
| --- | --- |
| `"remove"` | Works: removed articles keep a subsite URL. |
| `"keep"` | Works: other-language articles stay on the main site (and link there); each is listed once. |
| `"hide"` or unset (i18n_subsites' default) | i18n_subsites moves a new `Draft` copy of each subsite-only article to the main site's drafts; the published original stays in `generated_content` with no subsite URL and no page. The plugin skips articles whose source path is in `generator.drafts`, so they are left out instead of being listed with a dead link. Translations of main-site articles are unaffected. The plugin logs a warning. |

## Feed `<id>`

Pelican uses the site URL as the `<id>` of every feed of a site, so the main
language feed and the all-language feed of the main site share one id. With
`I18N_FEEDS_URL_AS_ID = True`, the `feed_generated` handler replaces it with
the feed's own URL, for the main site and the subsites. Prefixes in
`I18N_FEEDS_KEEP_ID_PREFIXES` are compared with the feed URL's path without
its leading `/`; use them for feed URLs that already have subscribers.
Entry ids are never changed.

## The `FEED_DOMAIN` fix

Pelican sets `FEED_DOMAIN = SITEURL` when it reads the main settings, before
`i18n_subsites` sets the subsite `SITEURL`. Subsites inherit the main
`FEED_DOMAIN`, so their `<head>` links and Atom self links would miss the
`/<lang>/` prefix. `feed_settings()` sets each subsite's `FEED_DOMAIN` to its
own URL (`SITEURL/<lang>`, or the subsite's `SITEURL` override).

## Tested versions

The test suite builds real sites in a subprocess (Pelican with the `simple`
theme). It passes with Pelican 4.7.0, 4.8.0, 4.9.0 and 4.12.0 (each with
`pelican-i18n-subsites` 1.0.0), and with Pelican 4.12.0 and
`pelican-i18n-subsites` 0.9.0, on Python 3.11 and 3.14. Pelican 4.5 and 4.6 fail to import
with current Jinja2, so they are not supported.
