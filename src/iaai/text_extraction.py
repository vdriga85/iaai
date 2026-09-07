"""Versioned non-executing HTML extraction and exact Unicode character chunks."""

import re
from datetime import date, datetime

import bs4
from bs4 import BeautifulSoup

from iaai.corpus_domain import ExtractionArtifact, TextChunk, digest


def normalize_text(text):
    lines = [
        re.sub(r"[^\S\n]+", " ", line).strip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def extract_html(observation_id, body, charset, policy):
    warnings = [
        "STATIC_HTML_ONLY_COMPLETENESS_NOT_GUARANTEED",
        "SOURCE_METADATA_IS_PUBLISHER_DECLARED",
    ]
    soup = BeautifulSoup(body, "html.parser", from_encoding=charset)
    if soup.contains_replacement_characters:
        warnings.append("ENCODING_REPLACEMENT_CHARACTERS")
    title = soup.title.get_text(" ", strip=True) if soup.title else None

    def meta(*names):
        for name in names:
            item = soup.find("meta", attrs={"property": name}) or soup.find(
                "meta", attrs={"name": name}
            )
            if item and item.get("content", "").strip():
                return item["content"].strip()
        return None

    date_text, source_date = meta("article:published_time", "datePublished"), None
    if date_text:
        try:
            source_date = (
                date.fromisoformat(date_text)
                if len(date_text) == 10
                else datetime.fromisoformat(date_text.replace("Z", "+00:00")).date()
            )
        except ValueError:
            warnings.append("INVALID_PUBLICATION_DATE")
    author = meta("author")
    js_hint = bool(soup.find("script"))
    for tag in soup.find_all(
        [
            "script",
            "style",
            "noscript",
            "template",
            "head",
            "nav",
            "footer",
            "svg",
            "canvas",
            "iframe",
            "form",
        ]
    ):
        tag.decompose()
    for tag in soup.find_all(attrs={"hidden": True}):
        tag.decompose()
    for tag in soup.find_all():
        if tag.attrs is None:
            continue
        style = tag.get("style", "").replace(" ", "").lower()
        if (
            tag.get("aria-hidden") == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        ):
            tag.decompose()
    for tag in soup.find_all(
        ["p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "tr", "br", "blockquote"]
    ):
        tag.insert_before("\n")
        tag.insert_after("\n")
    text = normalize_text(soup.get_text())
    status = "EXTRACTED" if text else "INCOMPLETE"
    if (js_hint and not text) or re.search(
        r"enable javascript|javascript (is )?required", text, re.I
    ):
        status = "INCOMPLETE"
        warnings.append("JAVASCRIPT_RENDERING_UNSUPPORTED")
    if len(text) > policy.max_text_chars:
        text, status = "", "FAILED"
        warnings.append("TEXT_LIMIT")
    return ExtractionArtifact(
        artifact_id="art_" + observation_id,
        observation_id=observation_id,
        text=text,
        text_hash=digest(text),
        extractor_version=f"html-block-v1/bs4-{bs4.__version__}",
        encoding=soup.original_encoding,
        language=None,
        title=title or None,
        author=author,
        source_date=source_date,
        metadata_origin="HTML_DECLARED",
        status=status,
        warnings=tuple(warnings),
    )


def chunk_text(artifact, policy):
    chunks, start = [], 0
    while start < len(artifact.text):
        end = min(start + policy.chunk_chars, len(artifact.text))
        if end < len(artifact.text):
            boundary = artifact.text.rfind("\n", start, end)
            if boundary > start:
                end = boundary + 1
        text = artifact.text[start:end]
        if text.strip():
            identity = (
                f"{artifact.artifact_id}:{policy.chunking_version}:"
                f"{policy.chunk_chars}:{start}:{end}"
            )
            chunks.append(
                TextChunk(
                    chunk_id="chk_" + digest(identity),
                    artifact_id=artifact.artifact_id,
                    text_hash=artifact.text_hash,
                    start=start,
                    end=end,
                    text=text,
                    chunk_hash=digest(text),
                    chunking_version=policy.chunking_version,
                )
            )
        start = end
    return tuple(chunks)
