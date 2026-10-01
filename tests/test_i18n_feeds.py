"""Build real three-language sites in a subprocess and read their feeds.

Each build runs Pelican in a fresh interpreter: i18n_subsites keeps module
state and Pelican's signals stay connected across runs in one process.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from xml.etree import ElementTree

import pytest

from pelican import signals  # type: ignore[attr-defined]
from pelican.plugins.i18n_feeds import feed_settings, register
from pelican.plugins.i18n_feeds.i18n_feeds import (
    is_subsite,
    use_feed_url_as_id,
    write_feeds,
)

ATOM = {"atom": "http://www.w3.org/2005/Atom"}
SITEURL = "https://example.com"
FEED_MAX_ITEMS = 30
LANGUAGE_NAMES = {"zh-tw": "臺灣華語", "ja": "日本語", "en": "English"}
LABELS = {
    "zh-tw": "全部語言 / All languages",
    "ja": "すべての言語 / All languages",
}
SUBSITES = {"ja": {"SITENAME": "Test JA"}, "en": {"SITENAME": "Test EN"}}
SOCIAL = (("GitHub", "https://github.com/example"), ("RSS", f"{SITEURL}/old"))


def _feed_settings(subsites: dict[str, Any] = SUBSITES) -> dict[str, Any]:
    return feed_settings(
        siteurl=SITEURL,
        sitename="Test",
        default_lang="zh-tw",
        subsites=subsites,
        language_names=LANGUAGE_NAMES,
        all_languages_labels=LABELS,
        social=SOCIAL,
    )


def _write_post(
    posts: Path,
    name: str,
    lang: str,
    category: str,
    date: str = "2026-01-01",
    body: str = "",
) -> None:
    suffix = "" if lang == "zh-tw" else f"-{lang}"
    (posts / f"{name}{suffix}.md").write_text(
        f"Title: {name} {lang}\nSlug: {name}\nLang: {lang}\nDate: {date}\n"
        f"Category: {category}\n\n{name} {lang}\n\n{body}\n",
        encoding="utf-8",
    )


def _build(
    tmp_path: Path,
    write_posts: Callable[[Path], None],
    overrides: dict[str, Any] | None = None,
    expect_warning: bool = False,
) -> tuple[Path, str]:
    posts = tmp_path / "content" / "posts"
    posts.mkdir(parents=True)
    write_posts(posts)
    output = tmp_path / "output"
    settings: dict[str, Any] = {
        "PATH": str(tmp_path / "content"),
        "OUTPUT_PATH": str(output),
        "CACHE_PATH": str(tmp_path / "cache"),
        "SITEURL": SITEURL,
        "SITENAME": "Test",
        "AUTHOR": "Test",
        "TIMEZONE": "UTC",
        "DEFAULT_LANG": "zh-tw",
        # Without it, a subsite would read a file without Lang as its own.
        "DEFAULT_METADATA": {"lang": "zh-tw"},
        "THEME": "simple",
        "PLUGINS": ["pelican.plugins.i18n_subsites", "pelican.plugins.i18n_feeds"],
        "STATIC_PATHS": [],
        "AUTHOR_FEED_ATOM": None,
        "AUTHOR_FEED_RSS": None,
        "TRANSLATION_FEED_ATOM": None,
        "FEED_MAX_ITEMS": FEED_MAX_ITEMS,
        "I18N_UNTRANSLATED_ARTICLES": "remove",
        "I18N_FEEDS_URL_AS_ID": True,
        "I18N_FEEDS_KEEP_ID_PREFIXES": ["feeds/"],
        **_feed_settings(),
        **(overrides or {}),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                # Pelican().run() sets up no logging: without this, records
                # reach stderr through logging.lastResort, without a level.
                "import json, logging, sys; from pelican import Pelican; "
                "logging.basicConfig(format='%(levelname)s %(name)s: %(message)s'); "
                "from pelican.settings import read_settings; "
                "Pelican(read_settings(override=json.load(sys.stdin))).run()"
            ),
        ],
        input=json.dumps(settings),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    log = result.stdout + result.stderr
    assert result.returncode == 0, log
    assert ("WARNING" in log) is expect_warning, log
    return output, log


def _read_feed(path: Path) -> dict[str, Any]:
    root = ElementTree.parse(path).getroot()
    entries = []
    for entry in root.findall("atom:entry", ATOM):
        link = entry.find("atom:link", ATOM)
        entry_id = entry.find("atom:id", ATOM)
        published = entry.find("atom:published", ATOM)
        content = entry.find("atom:content", ATOM)
        assert link is not None and entry_id is not None and published is not None
        entries.append(
            {
                "link": link.get("href"),
                "id": entry_id.text,
                "published": published.text,
                "content": "" if content is None else content.text or "",
            }
        )
    self_link = next(
        link.get("href")
        for link in root.findall("atom:link", ATOM)
        if link.get("rel") == "self"
    )
    feed_id = root.find("atom:id", ATOM)
    assert feed_id is not None
    return {
        "id": feed_id.text,
        "self": self_link,
        "entries": entries,
        "links": [entry["link"] for entry in entries],
    }


def _written_feeds(output: Path) -> list[str]:
    return sorted(
        path.relative_to(output).as_posix() for path in output.rglob("*.atom.xml")
    )


def _head_feed_links(html: Path) -> list[str]:
    return re.findall(
        r'<link href="([^"]+)" type="application/atom\+xml"',
        html.read_text(encoding="utf-8"),
    )


def _every_kind_of_post(posts: Path) -> None:
    # A zh article with ja and en translations; a ja-only article linking to
    # the ja translation; an en-only and a zh-only article.
    _write_post(posts, "review-post", "zh-tw", "Review", "2026-01-05")
    _write_post(posts, "review-post", "ja", "Review", "2026-01-05")
    _write_post(posts, "review-post", "en", "Review", "2026-01-05")
    _write_post(
        posts,
        "travel-post",
        "ja",
        "Travel",
        "2026-01-04",
        body="[review]({filename}review-post-ja.md)",
    )
    _write_post(posts, "tech-post", "en", "Tech", "2026-01-03")
    _write_post(posts, "cook-post", "zh-tw", "Cook", "2026-01-02")
    # Neither a draft nor a page belongs in a feed.
    (posts / "draft-post-en.md").write_text(
        "Title: draft\nSlug: draft-post\nLang: en\nDate: 2026-01-06\n"
        "Category: Tech\nStatus: draft\n\ndraft\n",
        encoding="utf-8",
    )
    pages = posts.parent / "pages"
    pages.mkdir()
    (pages / "about.md").write_text("Title: about\n\nabout\n", encoding="utf-8")


ZH_REVIEW = f"{SITEURL}/review-post.html"
JA_REVIEW = f"{SITEURL}/ja/review-post.html"
EN_REVIEW = f"{SITEURL}/en/review-post.html"
JA_TRAVEL = f"{SITEURL}/ja/travel-post.html"
EN_TECH = f"{SITEURL}/en/tech-post.html"
ZH_COOK = f"{SITEURL}/cook-post.html"
# Newest first; the three review-post versions share a date and keep the
# site order: the site article, then the others by file path.
EXPECTED = {
    "feeds/all.atom.xml": [
        ZH_REVIEW,
        EN_REVIEW,
        JA_REVIEW,
        JA_TRAVEL,
        EN_TECH,
        ZH_COOK,
    ],
    "feeds/review.atom.xml": [ZH_REVIEW, EN_REVIEW, JA_REVIEW],
    "feeds/travel.atom.xml": [JA_TRAVEL],
    "feeds/tech.atom.xml": [EN_TECH],
    "feeds/cook.atom.xml": [ZH_COOK],
    "zh-tw/feeds/all.atom.xml": [ZH_REVIEW, ZH_COOK],
    "zh-tw/feeds/review.atom.xml": [ZH_REVIEW],
    "zh-tw/feeds/cook.atom.xml": [ZH_COOK],
    "ja/feeds/all.atom.xml": [JA_REVIEW, JA_TRAVEL],
    "ja/feeds/review.atom.xml": [JA_REVIEW],
    "ja/feeds/travel.atom.xml": [JA_TRAVEL],
    "en/feeds/all.atom.xml": [EN_REVIEW, EN_TECH],
    "en/feeds/review.atom.xml": [EN_REVIEW],
    "en/feeds/tech.atom.xml": [EN_TECH],
}


def test_three_languages_split_feeds_with_every_article_in_feeds(
    tmp_path: Path,
) -> None:
    output, _ = _build(tmp_path, _every_kind_of_post)

    assert _written_feeds(output) == sorted(EXPECTED)
    feeds = {path: _read_feed(output / path) for path in EXPECTED}
    assert {path: feed["links"] for path, feed in feeds.items()} == EXPECTED
    for path, feed in feeds.items():
        assert len(set(feed["links"])) == len(feed["links"])
        assert feed["self"] == f"{SITEURL}/{path}"
        if path.startswith("feeds/"):
            # I18N_FEEDS_KEEP_ID_PREFIXES: subscribers keep Pelican's id.
            assert feed["id"] == f"{SITEURL}/"
        else:
            assert feed["id"] == feed["self"]

    # The ja-only article is the same entry in the main and the ja feeds, and
    # its relative link resolves to the ja subsite in both.
    main_entry = feeds["feeds/all.atom.xml"]["entries"][3]
    ja_entry = feeds["ja/feeds/all.atom.xml"]["entries"][1]
    assert main_entry == ja_entry
    assert f'href="{JA_REVIEW}"' in main_entry["content"]
    en_entry = feeds["feeds/all.atom.xml"]["entries"][4]
    assert en_entry == feeds["en/feeds/all.atom.xml"]["entries"][1]


def test_each_site_links_its_own_feeds_in_head(tmp_path: Path) -> None:
    output, _ = _build(tmp_path, _every_kind_of_post)

    # The simple theme links FEED_ATOM (and the category feed on category
    # pages) from FEED_DOMAIN: the subsites' links must carry /<lang>/.
    for lang, prefix in (("zh-tw", "zh-tw/"), ("ja", "ja/"), ("en", "en/")):
        site = output if lang == "zh-tw" else output / lang
        assert _head_feed_links(site / "index.html") == [
            f"{SITEURL}/{prefix}feeds/all.atom.xml"
        ]
    assert f"{SITEURL}/en/feeds/tech.atom.xml" in _head_feed_links(
        output / "en" / "category" / "tech.html"
    )


def test_feed_ids_default_to_pelicans(tmp_path: Path) -> None:
    output, _ = _build(
        tmp_path,
        _every_kind_of_post,
        {"I18N_FEEDS_URL_AS_ID": False},
    )

    for path in EXPECTED:
        # Pelican's id is the SITEURL of the site that writes the feed.
        lang = path.split("/")[0]
        site = f"{SITEURL}/{lang}/" if lang in SUBSITES else f"{SITEURL}/"
        assert _read_feed(output / path)["id"] == site


def test_articles_with_the_same_date_keep_the_site_order(tmp_path: Path) -> None:
    def write_posts(posts: Path) -> None:
        # Subsite-only names sort before the zh ones, so reading order cannot
        # produce the expected order by accident.
        for index in range(3):
            _write_post(posts, f"z-zh-{index}", "zh-tw", "Travel")
            _write_post(posts, f"a-ja-{index}", "ja", "Travel")
            _write_post(posts, f"b-en-{index}", "en", "Travel")
        # A zh article without an en version would be two "originals" on the
        # en subsite, which Pelican warns about: translate it everywhere.
        for lang in ("zh-tw", "ja", "en"):
            _write_post(posts, "m-both", lang, "Travel")

    output, _ = _build(tmp_path, write_posts)

    links = _read_feed(output / "feeds/all.atom.xml")["links"]
    site = {f"{SITEURL}/z-zh-{index}.html" for index in range(3)}
    site.add(f"{SITEURL}/m-both.html")
    # Site articles first (in the site's order), then their translations,
    # then the articles only another subsite publishes, by file path.
    assert set(links[:4]) == site
    assert set(links[4:6]) == {f"{SITEURL}/{lang}/m-both.html" for lang in ("ja", "en")}
    assert links[6:] == [
        *(f"{SITEURL}/ja/a-ja-{index}.html" for index in range(3)),
        *(f"{SITEURL}/en/b-en-{index}.html" for index in range(3)),
    ]


def test_all_language_feeds_keep_the_newest_items_up_to_the_limit(
    tmp_path: Path,
) -> None:
    langs = ("zh-tw", "ja", "en")

    def write_posts(posts: Path) -> None:
        for day in range(1, FEED_MAX_ITEMS + 6):
            date = f"2026-03-{day:02d}" if day <= 31 else f"2026-04-{day - 31:02d}"
            _write_post(posts, f"post-{day:02d}", langs[day % 3], "Travel", date)

    output, _ = _build(tmp_path, write_posts)

    for path in ("feeds/all.atom.xml", "feeds/travel.atom.xml"):
        entries = _read_feed(output / path)["entries"]
        published = [entry["published"] for entry in entries]
        assert len(entries) == FEED_MAX_ITEMS
        assert len({entry["link"] for entry in entries}) == FEED_MAX_ITEMS
        assert published == sorted(published, reverse=True)
        # The oldest posts fall off: post-01 .. post-05.
        slugs = {entry["link"].rsplit("/", 1)[1] for entry in entries}
        assert slugs == {f"post-{day:02d}.html" for day in range(6, FEED_MAX_ITEMS + 6)}
        for prefix in ("/ja/", "/en/"):
            assert any(prefix in entry["link"] for entry in entries)
        assert any(
            "/ja/" not in entry["link"] and "/en/" not in entry["link"]
            for entry in entries
        )


def test_hidden_untranslated_articles_are_reported(tmp_path: Path) -> None:
    output, log = _build(
        tmp_path,
        _every_kind_of_post,
        {"I18N_UNTRANSLATED_ARTICLES": "hide"},
        expect_warning=True,
    )

    assert "I18N_UNTRANSLATED_ARTICLES is 'hide'" in log
    # What the warning is about: the subsite-only articles drop out.
    links = _read_feed(output / "feeds/all.atom.xml")["links"]
    assert JA_TRAVEL not in links
    assert EN_TECH not in links


def test_kept_untranslated_articles_are_listed_once(tmp_path: Path) -> None:
    output, _ = _build(
        tmp_path, _every_kind_of_post, {"I18N_UNTRANSLATED_ARTICLES": "keep"}
    )

    links = _read_feed(output / "feeds/all.atom.xml")["links"]
    # Kept on the main site, the subsite-only articles link there
    # (ARTICLE_LANG_URL).
    assert links == [
        *(ZH_REVIEW, EN_REVIEW, JA_REVIEW),
        *(f"{SITEURL}/travel-post-ja.html", f"{SITEURL}/tech-post-en.html", ZH_COOK),
    ]


def test_without_subsites_the_feed_holds_articles_and_translations(
    tmp_path: Path,
) -> None:
    output, _ = _build(
        tmp_path,
        _every_kind_of_post,
        {"PLUGINS": ["pelican.plugins.i18n_feeds"], "I18N_SUBSITES": {}},
    )

    links = _read_feed(output / "feeds/all.atom.xml")["links"]
    assert len(links) == len(set(links)) == 6
    assert _written_feeds(output)[0] == "feeds/all.atom.xml"


def test_feed_settings_shape() -> None:
    result = _feed_settings()

    assert result["FEED_ALL_ATOM"] is None
    assert result["FEED_ATOM"] == "zh-tw/feeds/all.atom.xml"
    assert result["CATEGORY_FEED_ATOM"] == "zh-tw/feeds/{slug}.atom.xml"
    assert result["FEED_ALL_LANGUAGES_ATOM"] == "feeds/all.atom.xml"
    assert result["CATEGORY_FEED_ALL_LANGUAGES_ATOM"] == "feeds/{slug}.atom.xml"
    all_url = f"{SITEURL}/feeds/all.atom.xml"
    urls = {
        "zh-tw": f"{SITEURL}/zh-tw/feeds/all.atom.xml",
        "ja": f"{SITEURL}/ja/feeds/all.atom.xml",
        "en": f"{SITEURL}/en/feeds/all.atom.xml",
    }
    assert result["I18N_FEEDS_URLS"] == urls
    assert result["I18N_FEEDS_ALL_LANGUAGES_URL"] == all_url
    assert result["FEED_LINK_TITLES"] == {
        "FEED_ATOM": "Test — 臺灣華語",
        "CATEGORY_FEED_ATOM": "Test — 臺灣華語 — {name}",
    }
    assert result["FEED_EXTRA_LINKS"] == (("Test — 全部語言 / All languages", all_url),)
    assert dict(result["SOCIAL"])["RSS"] == urls["zh-tw"]

    subsites = result["I18N_SUBSITES"]
    assert set(subsites) == {"ja", "en"}
    for lang, site in subsites.items():
        assert site["SITENAME"] == SUBSITES[lang]["SITENAME"]
        assert site["FEED_DOMAIN"] == f"{SITEURL}/{lang}"
        assert site["FEED_ATOM"] == "feeds/all.atom.xml"
        assert site["CATEGORY_FEED_ATOM"] == "feeds/{slug}.atom.xml"
        assert site["FEED_LINK_TITLES"]["FEED_ATOM"] == (
            f"Test {lang.upper()} — {LANGUAGE_NAMES[lang]}"
        )
        assert site["FEED_EXTRA_LINKS"][0][1] == all_url
        assert dict(site["SOCIAL"]) == {
            "GitHub": "https://github.com/example",
            "RSS": urls[lang],
        }
    assert subsites["ja"]["FEED_EXTRA_LINKS"][0][0] == (
        "Test JA — すべての言語 / All languages"
    )
    # No label for en: the default one.
    assert subsites["en"]["FEED_EXTRA_LINKS"][0][0] == "Test EN — All languages"
    # The input is not modified.
    assert SUBSITES == {"ja": {"SITENAME": "Test JA"}, "en": {"SITENAME": "Test EN"}}


def test_feed_settings_options() -> None:
    result = feed_settings(
        siteurl=f"{SITEURL}/",
        sitename="Test",
        default_lang="en",
        subsites={
            "ja": {"SITEURL": "https://ja.example.com", "SOCIAL": (("feed", "x"),)},
            "de": {},
        },
        language_names={},
        feed_path="atom.xml",
        category_feed_path="atom/{slug}.xml",
        separator=" | ",
    )

    assert "SOCIAL" not in result
    assert "SOCIAL" not in result["I18N_SUBSITES"]["de"]
    # A subsite SOCIAL is left alone without the main one.
    assert result["I18N_SUBSITES"]["ja"]["SOCIAL"] == (("feed", "x"),)
    assert result["I18N_FEEDS_URLS"] == {
        "en": f"{SITEURL}/en/atom.xml",
        "ja": "https://ja.example.com/atom.xml",
        "de": f"{SITEURL}/de/atom.xml",
    }
    assert result["I18N_SUBSITES"]["ja"]["FEED_DOMAIN"] == "https://ja.example.com"
    assert result["CATEGORY_FEED_ATOM"] == "en/atom/{slug}.xml"
    # Without a language name, the code.
    assert result["I18N_SUBSITES"]["de"]["FEED_LINK_TITLES"]["FEED_ATOM"] == (
        "Test | de"
    )
    with pytest.raises(ValueError, match="also a subsite"):
        feed_settings(
            siteurl=SITEURL,
            sitename="Test",
            default_lang="ja",
            subsites={"ja": {}},
            language_names={},
        )


def test_is_subsite() -> None:
    assert not is_subsite({"DEFAULT_LANG": "zh-tw", "I18N_SUBSITES": {"ja": {}}})
    assert is_subsite({"DEFAULT_LANG": "ja", "I18N_SUBSITES": {"ja": {}}})
    assert not is_subsite({"DEFAULT_LANG": "ja"})


def test_subsites_and_unset_settings_write_nothing() -> None:
    class Writer:
        def write_feed(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("no feed expected")

    for settings in (
        {"DEFAULT_LANG": "zh-tw"},
        {
            "DEFAULT_LANG": "ja",
            "I18N_SUBSITES": {"ja": {}},
            "FEED_ALL_LANGUAGES_ATOM": "feeds/all.atom.xml",
        },
    ):
        write_feeds(SimpleNamespace(settings=settings), Writer())


@pytest.mark.parametrize(
    ("context", "url", "expected"),
    [
        ({}, f"{SITEURL}/ja/feeds/all.atom.xml", "site"),
        (
            {"I18N_FEEDS_URL_AS_ID": True},
            f"{SITEURL}/feeds/all.atom.xml",
            f"{SITEURL}/feeds/all.atom.xml",
        ),
        (
            {"I18N_FEEDS_URL_AS_ID": True, "I18N_FEEDS_KEEP_ID_PREFIXES": "feeds/"},
            f"{SITEURL}/feeds/all.atom.xml",
            "site",
        ),
        (
            {"I18N_FEEDS_URL_AS_ID": True, "I18N_FEEDS_KEEP_ID_PREFIXES": ["feeds/"]},
            f"{SITEURL}/ja/feeds/all.atom.xml",
            f"{SITEURL}/ja/feeds/all.atom.xml",
        ),
    ],
)
def test_use_feed_url_as_id(context: dict[str, Any], url: str, expected: str) -> None:
    feed = SimpleNamespace(feed={"feed_url": url, "id": "site"})

    use_feed_url_as_id(context, feed)

    assert feed.feed["id"] == expected


def test_register_connects_the_handlers() -> None:
    register()

    # blinker keys function receivers by id().
    assert id(write_feeds) in signals.article_writer_finalized.receivers
    assert id(use_feed_url_as_id) in signals.feed_generated.receivers
