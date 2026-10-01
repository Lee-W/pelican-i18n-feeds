"""Write Atom feeds that list the articles of every i18n_subsites language.

Pelican's ``FEED_ALL_ATOM`` lists the site's articles plus their translations,
so an article that only exists in a subsite language (a Japanese article
without a Chinese original) never appears in it. Worse, ``i18n_subsites``
removes every other-language article from the main site, so the main site's
feeds only hold its own language.

``FEED_ALL_LANGUAGES_ATOM`` and ``CATEGORY_FEED_ALL_LANGUAGES_ATOM`` write
feeds that also take the articles ``i18n_subsites`` removed from the main
site because a subsite publishes them. Only the main site writes them.

How it relies on ``i18n_subsites`` (1.0.0): the subsites are built from the
main site's ``get_writer`` signal, and the last one rewrites the URLs of the
removed articles to their subsite (``ja/...``) before any site writes a file.
So when the main site writes these feeds, its own copies of those articles
already link to the subsite. That requires
``I18N_UNTRANSLATED_ARTICLES = "remove"`` (or ``"keep"``): ``"hide"`` — the
plugin's default — turns them into hidden articles without a subsite URL, and
they drop out of these feeds; the plugin logs a warning in that case.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from operator import attrgetter
from typing import Any
from urllib.parse import urlparse

from pelican.contents import Article
from pelican.utils import order_content

from pelican import signals  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)

FEED_SETTING = "FEED_ALL_LANGUAGES_ATOM"
CATEGORY_FEED_SETTING = "CATEGORY_FEED_ALL_LANGUAGES_ATOM"


def is_subsite(settings: Mapping[str, Any]) -> bool:
    """Return whether these settings belong to an i18n_subsites subsite.

    i18n_subsites builds each subsite from a copy of the main settings with
    ``DEFAULT_LANG`` set to the subsite's language, so a site whose language
    is a key of ``I18N_SUBSITES`` is a subsite.
    """
    return settings.get("DEFAULT_LANG") in (settings.get("I18N_SUBSITES") or {})


def all_language_articles(generator: Any) -> list[Article]:
    """Return the published articles of every language once, in site order."""
    # Pelican's FEED_ALL_ATOM order: site articles, then their translations.
    items = list(generator.articles)
    for article in generator.articles:
        items.extend(article.translations)
    # generated_content also holds the articles i18n_subsites removed because
    # another subsite publishes them. Sort by path: files are read in no fixed
    # order, and articles with the same date keep the order they come in.
    items.extend(
        sorted(
            (
                content
                for content in generator.context["generated_content"].values()
                if isinstance(content, Article) and content.status == "published"
            ),
            key=attrgetter("source_path"),
        )
    )
    seen = set()
    articles = []
    for article in items:
        if article.source_path not in seen:
            seen.add(article.source_path)
            articles.append(article)
    ordered: list[Article] = order_content(
        articles, order_by=generator.settings["ARTICLE_ORDER_BY"]
    )
    return ordered


def _warn_on_hidden_articles(settings: Mapping[str, Any]) -> None:
    if not settings.get("I18N_SUBSITES"):
        return
    if settings.get("I18N_UNTRANSLATED_ARTICLES", "hide") == "hide":
        logger.warning(
            "i18n_feeds: I18N_UNTRANSLATED_ARTICLES is 'hide' (i18n_subsites' "
            "default); articles that only exist in a subsite language are left "
            "out of %s. Set it to 'remove' or 'keep'.",
            FEED_SETTING,
        )


def write_feeds(generator: Any, writer: Any) -> None:
    """Write the all-language site feed and category feeds of the main site."""
    settings = generator.settings
    path = settings.get(FEED_SETTING)
    category_path = settings.get(CATEGORY_FEED_SETTING)
    if (not path and not category_path) or is_subsite(settings):
        return
    _warn_on_hidden_articles(settings)
    articles = all_language_articles(generator)
    if path:
        writer.write_feed(
            articles,
            generator.context,
            path,
            settings.get(f"{FEED_SETTING}_URL", path),
        )
    if not category_path:
        return
    category_url = settings.get(f"{CATEGORY_FEED_SETTING}_URL", category_path)
    by_category: dict[Any, list[Article]] = defaultdict(list)
    for article in articles:
        by_category[article.category].append(article)
    for category, items in by_category.items():
        writer.write_feed(
            items,
            generator.context,
            str(category_path).format(slug=category.slug),
            str(category_url).format(slug=category.slug),
            feed_title=category.name,
        )


def use_feed_url_as_id(context: Mapping[str, Any], feed: Any) -> None:
    """Give a feed its own URL as ``<id>`` when ``I18N_FEEDS_URL_AS_ID`` is on.

    Pelican uses the site URL as the id of every feed of a site. Feeds whose
    URL path (without the leading slash) starts with one of
    ``I18N_FEEDS_KEEP_ID_PREFIXES`` keep that id, so existing subscribers of
    those URLs see no change.
    """
    if not context.get("I18N_FEEDS_URL_AS_ID"):
        return
    url = feed.feed["feed_url"]
    path = urlparse(url).path.lstrip("/")
    keep: Iterable[str] = context.get("I18N_FEEDS_KEEP_ID_PREFIXES") or ()
    if isinstance(keep, str):
        keep = (keep,)
    if any(path.startswith(prefix) for prefix in keep):
        return
    feed.feed["id"] = url


def _with_rss(
    social: Sequence[Sequence[str]], url: str, rss_names: Iterable[str]
) -> tuple[tuple[str, str], ...]:
    names = {name.lower() for name in rss_names}
    return tuple(
        (name, url if name.lower() in names else link) for name, link in social
    )


def feed_settings(
    *,
    siteurl: str,
    sitename: str,
    default_lang: str,
    subsites: Mapping[str, Mapping[str, Any]],
    language_names: Mapping[str, str],
    all_languages_labels: Mapping[str, str] | None = None,
    social: Sequence[Sequence[str]] | None = None,
    feed_path: str = "feeds/all.atom.xml",
    category_feed_path: str = "feeds/{slug}.atom.xml",
    separator: str = " — ",
    rss_names: Iterable[str] = ("rss",),
) -> dict[str, Any]:
    """Return the publish settings for one feed per language plus all languages.

    Layout (with the default paths)::

        feeds/all.atom.xml, feeds/{slug}.atom.xml          every language
        <default_lang>/feeds/all.atom.xml, .../{slug}...   the main language
        <lang>/feeds/all.atom.xml, .../{slug}...           each subsite

    The result holds the main site's settings plus a new ``I18N_SUBSITES``
    (``subsites`` is not modified) whose entries gain each subsite's feed
    settings, and ``SOCIAL`` when ``social`` is given. Unpack it into the
    settings module, e.g. ``globals().update(feed_settings(...))``.

    Each site gets ``FEED_LINK_TITLES`` (its language feed and category feeds)
    and ``FEED_EXTRA_LINKS`` (the all-language feed) in the shape attila
    >= 3.5.0 reads; other themes ignore them. ``I18N_FEEDS_URLS`` maps every
    language to its feed URL and ``I18N_FEEDS_ALL_LANGUAGES_URL`` is the
    all-language feed URL, for templates or your own settings.

    Args:
        siteurl: The production ``SITEURL`` of the main site.
        sitename: The main site's ``SITENAME``; a subsite's own ``SITENAME``
            override is used for its titles when present.
        default_lang: The main site's ``DEFAULT_LANG``.
        subsites: ``I18N_SUBSITES``.
        language_names: Language code to the name used in feed titles.
        all_languages_labels: Language code to the label of the all-language
            feed link on that language's pages (default ``"All languages"``).
        social: The main site's ``SOCIAL``. When given, the entry named like
            ``rss_names`` (case-insensitive) points at each site's own feed;
            a subsite without its own ``SOCIAL`` starts from this one.
        feed_path: Path of a site feed, relative to the site root.
        category_feed_path: Path of a category feed, with ``{slug}``.
        separator: Joins the parts of a feed title.
        rss_names: ``SOCIAL`` entry names that link to the feed.
    """
    if default_lang in subsites:
        raise ValueError(f"default_lang {default_lang!r} is also a subsite")
    siteurl = siteurl.rstrip("/")
    labels = all_languages_labels or {}
    all_url = f"{siteurl}/{feed_path}"
    site_urls = {
        lang: str(overrides.get("SITEURL") or f"{siteurl}/{lang}").rstrip("/")
        for lang, overrides in subsites.items()
    }
    urls = {default_lang: f"{siteurl}/{default_lang}/{feed_path}"}
    urls.update({lang: f"{url}/{feed_path}" for lang, url in site_urls.items()})

    def links(name: str, lang: str) -> dict[str, Any]:
        language = language_names.get(lang, lang)
        label = labels.get(lang, "All languages")
        return {
            "FEED_LINK_TITLES": {
                "FEED_ATOM": f"{name}{separator}{language}",
                "CATEGORY_FEED_ATOM": f"{name}{separator}{language}{separator}{{name}}",
            },
            "FEED_EXTRA_LINKS": ((f"{name}{separator}{label}", all_url),),
            "I18N_FEEDS_URLS": dict(urls),
            "I18N_FEEDS_ALL_LANGUAGES_URL": all_url,
        }

    new_subsites: dict[str, dict[str, Any]] = {}
    for lang, overrides in subsites.items():
        site = {
            **overrides,
            # Pelican derives FEED_DOMAIN from the main SITEURL before the
            # subsite exists, so feed links and self links would miss /<lang>/.
            "FEED_DOMAIN": site_urls[lang],
            "FEED_ATOM": feed_path,
            "CATEGORY_FEED_ATOM": category_feed_path,
            **links(str(overrides.get("SITENAME", sitename)), lang),
        }
        base_social = overrides.get("SOCIAL", social)
        if social is not None and base_social is not None:
            site["SOCIAL"] = _with_rss(base_social, urls[lang], rss_names)
        new_subsites[lang] = site

    result: dict[str, Any] = {
        "FEED_ALL_ATOM": None,
        "FEED_ATOM": f"{default_lang}/{feed_path}",
        "CATEGORY_FEED_ATOM": f"{default_lang}/{category_feed_path}",
        FEED_SETTING: feed_path,
        CATEGORY_FEED_SETTING: category_feed_path,
        **links(sitename, default_lang),
        "I18N_SUBSITES": new_subsites,
    }
    if social is not None:
        result["SOCIAL"] = _with_rss(social, urls[default_lang], rss_names)
    return result


def register() -> None:
    """Connect the plugin to Pelican's signals."""
    signals.article_writer_finalized.connect(write_feeds)
    signals.feed_generated.connect(use_feed_url_as_id)
