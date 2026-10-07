import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from funneltrace.intake import InboundLead

MIN_PREFIX = 3  # "dan" is a plausible short form of "daniel"; "d" is not
MIN_SIMILARITY = 0.8  # typo tolerance: "jon"/"john" pass, "dan"/"don" do not


@dataclass(frozen=True)
class Candidate:
    lead_id: str
    name: str
    normalized_email: str | None
    normalized_phone: str | None


@dataclass(frozen=True)
class Match:
    lead_id: str
    reason: str


def _tokens(name: str) -> list[str]:
    return re.findall(r"[a-z]+", name.lower())


def _has_real_name(name: str) -> bool:
    # WhatsApp leads without a profile name fall back to "+<number>".
    return not name.startswith("+") and bool(_tokens(name))


def _similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= MIN_SIMILARITY


def _first_names_match(a: str, b: str) -> bool:
    short, long_ = sorted((a, b), key=len)
    return a == b or (len(short) >= MIN_PREFIX and long_.startswith(short)) or _similar(a, b)


def _last_names_match(a: str, b: str) -> bool:
    short, long_ = sorted((a, b), key=len)
    return a == b or (len(short) == 1 and long_.startswith(short)) or _similar(a, b)


def names_compatible(a: str, b: str) -> bool:
    """Could these two names belong to the same person? Used only to confirm a match
    on email/phone, never to create one."""
    if not (_has_real_name(a) and _has_real_name(b)):
        return True
    ta, tb = _tokens(a), _tokens(b)
    if not _first_names_match(ta[0], tb[0]):
        return False
    if len(ta) > 1 and len(tb) > 1:
        return _last_names_match(ta[-1], tb[-1])
    return True


def merged_name(existing: str, incoming: str) -> str:
    """Keep the more complete name when merging ("Priya" + "Priya Sharma")."""
    if not _has_real_name(existing):
        return incoming
    if not _has_real_name(incoming):
        return existing
    return incoming if len(_tokens(incoming)) > len(_tokens(existing)) else existing


def find_match(inbound: InboundLead, candidates: list[Candidate]) -> Match | None:
    best: Match | None = None
    for c in candidates:
        by_email = bool(inbound.normalized_email) and inbound.normalized_email == c.normalized_email
        by_phone = bool(inbound.normalized_phone) and inbound.normalized_phone == c.normalized_phone
        if not (by_email or by_phone) or not names_compatible(inbound.name, c.name):
            continue
        keys = "+".join(k for k, hit in (("email", by_email), ("phone", by_phone)) if hit)
        if _has_real_name(inbound.name) and _has_real_name(c.name):
            name_note = f"name '{inbound.name}' ~ '{c.name}'"
        else:
            name_note = "no usable name to compare"
        match = Match(c.lead_id, f"normalized {keys} match; {name_note}")
        if by_email and by_phone:
            return match
        best = best or match
    return best
