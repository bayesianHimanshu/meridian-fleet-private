"""openFDA queries for portfolio.safety_signal_scout (phase 5 step 3a; docs/signal-scout.md):
the count queries, the label query, the records of what each returned, and the fetch
loop. The loop takes a get function, so it runs with httpx inside the portfolio_signal
sandbox and with recorded responses or a fake anywhere else; nothing here reads study
data. Count queries only on the event endpoint, no API key.
"""

import hashlib
import json
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from meridian.platform.agent_settings import SignalScoutConfig

EVENT = "/drug/event.json"
LABEL = "/drug/label.json"
REACTION_FIELD = "patient.reaction.reactionmeddrapt.exact"
RESPONSES_TABLE = "openfda_responses"

Get = Callable[[str, str], tuple[int, str]]  # (path, query string) -> (status, body)


@dataclass(frozen=True, slots=True)
class Response:
    """One request and what came back: the body exactly as received, its sha256 and
    openFDA's meta.last_updated (empty when the body has none)."""

    path: str
    query: str
    status: int
    body: str
    sha256: str
    last_updated: str

    @classmethod
    def of(cls, path: str, query: str, status: int, body: str) -> Response:
        return cls(
            path=path,
            query=query,
            status=status,
            body=body,
            sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            last_updated=_last_updated(body),
        )

    def json(self) -> dict[str, Any]:
        try:
            value = json.loads(self.body)
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}


def _last_updated(body: str) -> str:
    try:
        meta = json.loads(body).get("meta", {})
    except ValueError, AttributeError:
        return ""
    return str(meta.get("last_updated", "")) if isinstance(meta, dict) else ""


_SAFE = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-~")


def _encode(text: str) -> str:
    """Form encoding, as urllib.parse.quote_plus with safe="" (a test checks it): kept here
    so that meridian-worker's import closure, which reaches this module through the agent,
    stays free of every network module."""
    out = []
    for ch in text:
        if ch in _SAFE:
            out.append(ch)
        elif ch == " ":
            out.append("+")
        else:
            out.extend(f"%{b:02X}" for b in ch.encode("utf-8"))
    return "".join(out)


def _q(params: Sequence[tuple[str, str]]) -> str:
    return "&".join(f"{_encode(k)}={_encode(v)}" for k, v in params)


def product_search(cfg: SignalScoutConfig) -> str:
    return f'{cfg.product_field}:"{cfg.product_term}"'


def reactions_query(cfg: SignalScoutConfig) -> str:
    return _q(
        [("search", product_search(cfg)), ("count", REACTION_FIELD), ("limit", str(cfg.limit))]
    )


def drug_total_query(cfg: SignalScoutConfig) -> str:
    return _q([("search", product_search(cfg)), ("count", cfg.total_field)])


def all_total_query(cfg: SignalScoutConfig) -> str:
    return _q([("count", cfg.total_field)])


def term_total_query(cfg: SignalScoutConfig, term: str) -> str:
    return _q([("search", f'{REACTION_FIELD}:"{term}"'), ("count", cfg.total_field)])


def label_query(cfg: SignalScoutConfig) -> str:
    return _q([("search", f'openfda.generic_name.exact:"{cfg.product_term}"'), ("limit", "1")])


def counts(r: Response) -> list[tuple[str, int]]:
    """A count query's (term, count) pairs; empty for a 404 (openFDA's "no matches")."""
    results = r.json().get("results", [])
    if r.status != 200 or not isinstance(results, list):
        return []
    return [(str(x.get("term")), int(x.get("count", 0))) for x in results if isinstance(x, dict)]


def total(r: Response) -> int | None:
    """The sum of a count query's buckets (a report total), None when it did not answer."""
    if r.status == 404:
        return 0
    if r.status != 200:
        return None
    return sum(c for _, c in counts(r))


def fetch(
    get: Get,
    cfg: SignalScoutConfig,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Response]:
    """The pre-registered plan: the reaction terms, the drug's and all reports, the label,
    then one total for each term with at least min_reports reports with the drug, most
    reported first, never more than max_requests requests, pausing between them."""
    out: list[Response] = []

    def call(path: str, query: str) -> Response:
        if out:
            sleep(cfg.request_interval_seconds)
        status, body = get(path, query)
        r = Response.of(path, query, status, body)
        out.append(r)
        return r

    reactions = call(EVENT, reactions_query(cfg))
    call(EVENT, drug_total_query(cfg))
    call(EVENT, all_total_query(cfg))
    call(LABEL, label_query(cfg))
    terms = sorted(
        ((t, n) for t, n in counts(reactions) if n >= cfg.min_reports),
        key=lambda x: (-x[1], x[0]),
    )
    for term, _ in terms:
        if len(out) >= cfg.max_requests:
            break
        call(EVENT, term_total_query(cfg, term))
    return out


@dataclass(frozen=True, slots=True)
class Label:
    set_id: str
    version: str
    effective_time: str
    text: str  # adverse reactions, warnings and precautions, boxed warning: lower case
    most_common: tuple[str, ...]  # section 6's "most common adverse reactions"


_MOST_COMMON = re.compile(r"most common adverse reactions \([^)]*\) were ([^.]*)\.")
LABEL_SECTIONS = ("boxed_warning", "warnings_and_cautions", "adverse_reactions")


def normalise(text: str) -> str:
    """Lower case, punctuation as spaces, single spaces."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def label_of(r: Response) -> Label | None:
    results = r.json().get("results", [])
    if r.status != 200 or not results:
        return None
    doc = results[0]
    raw = " ".join(
        " ".join(doc.get(section, [])) for section in LABEL_SECTIONS if section in doc
    ).lower()
    m = _MOST_COMMON.search(" ".join(raw.split()))
    common: tuple[str, ...] = ()
    if m:
        parts = re.split(r",\s*|\s+and\s+", m.group(1))
        # An Oxford comma leaves "and x" after the split: the "and" is not part of x.
        common = tuple(p.strip().removeprefix("and ").strip() for p in parts if p.strip())
    return Label(
        set_id=str(doc.get("set_id", "")),
        version=str(doc.get("version", "")),
        effective_time=str(doc.get("effective_time", "")),
        text=normalise(raw),
        most_common=common,
    )


def listed(term: str, label: Label) -> bool:
    """The pre-registered rule: the term, lower-cased, as a phrase in the label's text
    (punctuation as spaces). No synonyms, no MedDRA hierarchy."""
    phrase = normalise(term)
    return bool(phrase) and f" {phrase} " in f" {label.text} "
