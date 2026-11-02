"""APA 7 reference formatting and parsing helpers for the csclbot reference data.

Formatting functions return Markdown (``*italics*``); use ``plain()`` for plain text.
Parsing turns Gerry's existing APA strings (e-library ``chapter_reference``) into fields.
"""
from __future__ import annotations

import html
import re
import unicodedata

PARTICLES = {"de", "van", "der", "den", "von", "la", "le", "di", "da", "del", "bin", "el", "al", "ten", "ter"}
JOURNAL_IJCSCL = "International Journal of Computer-Supported Collaborative Learning"


# ---------------------------------------------------------------- text helpers
def clean_text(text: str) -> str:
    """NFKC (ligatures, no-break spaces), strip JATS tags/entities, collapse whitespace."""
    text = html.unescape(re.sub(r"<[^>]+>", "", text or ""))
    text = unicodedata.normalize("NFKC", text).replace("\u2011", "-")
    return re.sub(r"\s+", " ", text).strip()


def norm_key(text: str) -> str:
    """Alphanumeric lower-case key for fuzzy equality of titles."""
    text = unicodedata.normalize("NFKD", clean_text(text).lower())
    return re.sub(r"[^a-z0-9]", "", text)


def plain(markdown: str) -> str:
    return markdown.replace("*", "")


def en_dash(pages: str) -> str:
    return re.sub(r"\s*[-\u2010\u2011\u2012\u2013\u2014]+\s*", "\u2013", pages.strip())


def sentence_case_if_shouting(title: str) -> str:
    """Convert ALL-CAPS titles to sentence case; leave everything else untouched."""
    letters = [c for c in title if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        low = title.lower()
        return low[:1].upper() + low[1:]
    return title


# ---------------------------------------------------------------- names
def initials_of(given: str) -> str:
    """'Hans-Rudiger' -> 'H.-R.', 'Christa S. C.' -> 'C. S. C.', 'J.W.' -> 'J. W.'."""
    out: list[str] = []
    for token in given.replace("\u2010", "-").split():
        if re.fullmatch(r"(?:[^\W\d_]\.)+", token):
            out.extend(c + "." for c in token if c != ".")
        elif "-" in token:
            out.append("-".join(p[0].upper() + "." for p in token.split("-") if p))
        elif token and token[0].isalpha():
            out.append(token[0].upper() + ".")
    return " ".join(out).replace(". -", ".-")


def author(family: str, given: str = "") -> dict:
    family = "Çakır" if family.strip() == "Çakir" else family.strip()  # Gerry's references drop the dotless i
    a = {"family": family, "given": given.strip()}
    a["initials"] = initials_of(given) if given else ""
    return a


def split_display_name(name: str) -> dict:
    """'Maarten de Laat' -> family 'de Laat'; single tokens and group names become literals."""
    name = clean_text(name)
    tokens = name.split()
    if len(tokens) < 2:
        return {"literal": name}
    i = len(tokens) - 1
    while i > 1 and tokens[i - 1].lower() in PARTICLES:
        i -= 1
    return author(" ".join(tokens[i:]), " ".join(tokens[:i]))


def authors_from_ampersand_string(text: str) -> list[dict]:
    """'Manu Kapur & Charles K. Kinzer' (or 'G. Stahl, T. Koschmann & D. Suthers')."""
    parts = [p for p in re.split(r"\s*(?:&|;|,(?!\s*(?:Jr|Sr)))\s*", text or "") if p.strip()]
    return [split_display_name(p) for p in parts]


def format_author_list(authors: list[dict]) -> str:
    def one(a: dict) -> str:
        if a.get("literal"):
            return a["literal"]
        return f"{a['family']}, {a['initials']}".rstrip(", ")

    names = [one(a) for a in authors]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) > 20:
        return ", ".join(names[:19]) + ", . . . " + names[-1]
    return ", ".join(names[:-1]) + ", & " + names[-1]


def cite_short(authors: list[dict], year: int | str | None) -> str:
    """APA in-text author-date, e.g. 'Kapur & Kinzer, 2009' / 'Stahl et al., 2014'."""
    fams = [a.get("family") or a.get("literal", "") for a in authors]
    if not fams:
        who = "Anon."
    elif len(fams) == 1:
        who = fams[0]
    elif len(fams) == 2:
        who = f"{fams[0]} & {fams[1]}"
    else:
        who = f"{fams[0]} et al."
    return f"{who}, {year}" if year else who


def format_editors(editors: list[dict]) -> str:
    """'G. Stahl (Ed.)' / 'A. Lund, & B. Smith (Eds.)' in initials-first order."""
    names = [f"{e['initials']} {e['family']}".strip() if not e.get("literal") else e["literal"] for e in editors]
    if not names:
        return ""
    if len(names) == 1:
        return f"{names[0]} (Ed.)"
    return (", ".join(names[:-1]) + (", & " if len(names) > 2 else " & ") + names[-1]) + " (Eds.)"


# ---------------------------------------------------------------- formatting
def _tail(doi: str | None, url: str | None) -> str:
    if doi:
        return f" https://doi.org/{doi}"
    return f" {url}" if url else ""


def _finish(authors: str, year: str, body: str, tail: str, original_year: str | None) -> str:
    ref = f"{authors} ({year}). {body}{tail}".replace("..", ".")
    if original_year and original_year != year:
        ref += f" (Original work published {original_year})"
    return ref.strip()


def format_journal(d: dict) -> str:
    vol = f"*{d['journal']}, {d['volume']}*" if d.get("volume") else f"*{d['journal']}*"
    issue = f"({d['issue']})" if d.get("issue") else ""
    loc = ""
    if d.get("pages"):
        loc = f", {d['pages']}"
    elif d.get("article_number"):
        loc = f", Article {d['article_number']}"
    title = d["title"] + (" [Editorial]" if d.get("subtype") == "editorial" else "")
    title = title if title[-1] in ".?!" else title + "."
    body = f"{title} {vol}{issue}{loc}."
    return _finish(format_author_list(d["authors"]), str(d["year"]), body, _tail(d.get("doi"), d.get("url")), d.get("original_year"))


def format_chapter(d: dict) -> str:
    title = d["title"] if d["title"][-1] in ".?!" else d["title"] + "."
    editors = d.get("editors_text") or format_editors(d.get("editors", []))
    where = f"In {editors}, " if editors else "In "
    pages = ""
    if d.get("pages"):
        label = "pp." if "\u2013" in d["pages"] else "p."
        extra = f"{d['volume_note']}, " if d.get("volume_note") else ""
        pages = f" ({extra}{label} {d['pages']})"
    pub = f" {d['publisher']}." if d.get("publisher") else ""
    body = f"{title} {where}*{d['book_title']}*{pages}.{pub}"
    return _finish(format_author_list(d["authors"]), str(d["year"]), body, _tail(d.get("doi"), d.get("url")), d.get("original_year"))


def format_conference(d: dict) -> str:
    title = d["title"] if d["title"][-1] in ".?!" else d["title"] + "."
    venue = d["venue"] + (f", {d['location']}" if d.get("location") else "")
    body = f"*{title.rstrip('.')}* [Paper presentation]. {venue}."
    return _finish(format_author_list(d["authors"]), str(d["year"]), body, _tail(d.get("doi"), d.get("url")), d.get("original_year"))


def format_standalone(d: dict) -> str:
    """Reports, theses, web pages and other stand-alone works: italic title, optional descriptor."""
    title = re.sub(r"\s*\([A-Z]{2,}-[\w-]+\)$", "", d["title"].rstrip("."))
    note = f" ({d['descriptor']})" if d.get("descriptor") and d["type"] == "report" else (
        f" [{d['descriptor']}]" if d.get("descriptor") else "")
    pub = f" {d['publisher']}." if d.get("publisher") else ""
    body = f"*{title}*{note}.{pub}"
    return _finish(format_author_list(d["authors"]), str(d["year"]), body, _tail(d.get("doi"), d.get("url")), d.get("original_year"))


FORMATTERS = {
    "journal_article": format_journal,
    "editorial": format_journal,
    "book_review": format_journal,
    "correction": format_journal,
    "book_chapter": format_chapter,
    "conference_paper": format_conference,
}


def format_reference(d: dict) -> str:
    return FORMATTERS.get(d["type"], format_standalone)(d)


# ---------------------------------------------------------------- parsing Gerry's APA strings
GLITCHES = [
    (r"\bInSawyer\b", "In R. K. Sawyer"),
    (r"&Sawyer\b", "& R. K. Sawyer"),
    (r"\bInSuthers,", "In D. D. Suthers,"),
]
AUTHOR_PAIR = re.compile(r"(?:^|,\s*|&\s*)(?P<fam>[^,&]+?),\s*(?P<ini>(?:[^\W\d_a-z]\.[\s-]*)+)")
REF_HEAD = re.compile(r"^(?P<authors>.+?)\s\((?P<year>\d{4})(?P<suffix>[a-z]?)(?:,[^)]*)?\)\.\s*(?P<rest>.*)$", re.S)
CHAPTER_VENUE = re.compile(
    r"^In\s+(?P<eds>.+?)\s*\((?P<ed>Eds?)\.\),?\s+(?P<book>.+?)"
    r"(?:\s*\((?P<paren>[^()]*)\))?\.\s*(?:(?P<place>[^:]+):\s*(?P<pub>.+?))?\.?$",
    re.S,
)
JOURNAL_VENUE = re.compile(
    r"^(?P<journal>.+?),?\s+(?:(?P<vol>\d{1,4}|[IVX]{1,5})(?:\((?P<issue>[^)]+)\))?)(?:,\s*(?P<pages>[A-Za-z]?\d+\s*[\u2013-]\s*[A-Za-z]?\d+))?\.?$"
    r"|^(?P<journal2>[^,]+),\s*(?P<pages2>\d+\s*[\u2013-]\s*\d+)\.?$"
)
CONF_WORDS = re.compile(
    r"conference|proceedings|workshop|symposium|convention|meeting|congress|conf\.|icls|cscl|icce|"
    r"annual|international society|e-learning|geogebra|aera|sig",
    re.I,
)


def parse_authors(text: str) -> list[dict]:
    text = clean_text(text)
    out, covered = [], 0
    for m in AUTHOR_PAIR.finditer(text):
        out.append(author(m.group("fam"), m.group("ini")))
        covered = m.end()
    leftover = re.sub(r"^[\s,&.]+", "", text[covered:])
    if leftover.strip(" ,.&"):
        out.append({"literal": leftover.strip(" ,&")})
    return out or [{"literal": text}]


def normalise_doi_url(url: str) -> tuple[str | None, str | None]:
    """Return (doi, url): doi.org / dx.doi.org links and ISBN-style Springer DOIs become bare DOIs."""
    url = url.rstrip(".,;")
    url = re.sub(r"^https?://(?:dx\.)?doi\.org/(?:https?://(?:dx\.)?doi\.org/)?", "https://doi.org/", url)
    m = re.match(r"https://doi\.org/(.+)$", url)
    if m:
        doi = m.group(1)
        if re.match(r"978-", doi):
            doi = "10.1007/" + doi
        return (doi, None) if doi.startswith("10.") else (None, None)
    return None, url


def _split_title_venue(rest: str) -> list[tuple[str, str]]:
    """Candidate (title, venue) splits at sentence ends, shortest title first."""
    splits = []
    for m in re.finditer(r"([.?!])\s+(?=\S)", rest):
        head = rest[: m.end(1)].strip()
        if m.group(1) != "." and len(head.split()) < 3:  # "POW! Perspectives on the Web" is one title
            continue
        splits.append((head, rest[m.end() :].strip()))
    return splits


def parse_reference(ref: str) -> dict:
    """Best-effort split of an APA string into fields; ``parse_ok`` False means use raw text."""
    raw = ref
    ref = clean_text(ref)
    for pat, repl in GLITCHES:
        ref = re.sub(pat, repl, ref)
    ref = re.sub(r",\s*Article\s+\d+", "", ref)
    ref = re.sub(r'(\d)\s+"[^"]*"\s*\(', r"\1(", ref)  # special-issue title squeezed between volume and issue
    ref = re.sub(r"(?<![.?!:])\s+(In\s+(?:[A-Z]\.\s*)+[A-Z][\w'-]+(?:,|\s*\(Eds?\.\)))", r". \1", ref)
    out: dict = {"raw": raw, "parse_ok": False, "type": "other"}
    head = REF_HEAD.match(ref)
    if not head:
        return out
    out.update(
        authors=parse_authors(head.group("authors")),
        year=int(head.group("year")),
        year_suffix=head.group("suffix"),
    )
    rest = head.group("rest").strip()

    urls = re.findall(r"https?://[^\s;]+", rest)
    rest = re.sub(r"\s*;?\s*https?://[^\s;]+", "", rest).strip()
    for u in urls:
        doi, url = normalise_doi_url(u)
        if doi and not out.get("doi"):
            out["doi"] = doi
        elif url and not out.get("url"):
            out["url"] = url
    rest = re.sub(r"\s*\[(?P<n>[^\]]*)\]", lambda m: (out.setdefault("notes", []).append(m.group("n")) or ""), rest)
    if any(re.search(r"review", n, re.I) for n in out.get("notes", [])):
        out["subtype"] = "book_review"
    rest = re.sub(r"\s+\.", ".", rest).strip()

    thesis = next((n for n in out.get("notes", []) if re.search(r"dissertation|thesis", n, re.I)), None)
    if thesis:
        title, _, venue = rest.partition(". ")
        descriptor = re.sub(r"^Ph\.?D\.? Dissertation", "Doctoral dissertation", thesis)
        descriptor = re.sub(r"^Bachelor Thesis", "Bachelor's thesis", descriptor)
        if "," not in descriptor and venue.strip(" ."):
            descriptor += f", {venue.strip(' .')}"
        out.update(type="thesis", title=title.strip(" ."), descriptor=descriptor, parse_ok=True)
        return out

    for title, venue in _split_title_venue(rest):
        venue = venue.strip()
        cm = CHAPTER_VENUE.match(venue)
        if cm:
            paren = cm.group("paren") or ""
            pages_m = re.search(r"pp?\.\s*(?P<pages>.+)$", paren)
            vol_m = re.match(r"(?P<vol>Vol\.[^,]*)", paren)
            out.update(
                type="book_chapter",
                title=title,
                editors_text=cm.group("eds").strip() + (" (Eds.)" if cm.group("ed") == "Eds" else " (Ed.)"),
                book_title=cm.group("book").strip(" ."),
                pages=en_dash(pages_m.group("pages")) if pages_m else None,
                volume_note=vol_m.group("vol").strip() if vol_m and pages_m else None,
                volume=vol_m.group("vol").strip() if vol_m else None,
                publisher=(cm.group("pub") or "").strip(" .") or None,
                parse_ok=True,
            )
            return out
        jm = JOURNAL_VENUE.match(venue)
        if jm and (jm.group("journal") or jm.group("journal2")):
            journal = re.split(r"\.\s*special", jm.group("journal") or jm.group("journal2"), flags=re.I)[0].strip(" .,")
            out.update(
                type="journal_article",
                title=title,
                journal=journal,
                volume=jm.group("vol"),
                issue=en_dash(jm.group("issue")) if jm.group("issue") else None,
                pages=en_dash(jm.group("pages") or jm.group("pages2") or "") or None,
                parse_ok=True,
            )
            return out
    # no recognised container: the remainder is a conference, report or web page
    for title, venue in _split_title_venue(rest):
        if CONF_WORDS.search(venue):
            loc_match = re.match(r"^(?P<conf>.+?),\s*(?P<loc>[^,]+(?:,\s*[^,]+)?)\.?$", venue)
            out.update(
                type="conference_paper",
                title=title,
                venue=(loc_match.group("conf") if loc_match else venue).strip(" ."),
                location=loc_match.group("loc").strip(" .") if loc_match else None,
                parse_ok=True,
            )
            return out
    title = rest.rstrip(". ")
    report = re.search(r"\((?P<num>[A-Z]{2,}-[\w-]+)\)$", title)
    out.update(
        type="report" if report else ("web_page" if out.get("url") else "other"),
        title=title,
        descriptor=f"Technical Report No. {report.group('num')}" if report else None,
        parse_ok=bool(report or (out.get("url") and not CONF_WORDS.search(title))),
    )
    return out
