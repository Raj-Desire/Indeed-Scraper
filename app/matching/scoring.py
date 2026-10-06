"""
Deterministic, evidence-based match scoring.

The LLM labels each JD requirement (covered/partial/none) and quotes KB text, but a small
model is unreliable in both directions, so the final verdict is decided in code from the
retrieved evidence itself: literal/alias phrase presence, token coverage, and quote
validity. The score is then computed from those verdicts, so it is reproducible.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

IMPORTANCE_WEIGHT = {"must": 3.0, "nice": 1.0}
VERDICT_CREDIT = {"covered": 1.0, "partial": 0.5, "none": 0.0}
# Role-level fit caps the score: many incidental tool matches must not lift a role
# whose core work is outside our service lines.
ROLE_FIT_CAP = {"strong": 100, "partial": 90, "weak": 40}

# Equivalent surface forms (all lower-case, punctuation-free). Extend via config/skill_aliases.json:
# {"rag": ["retrieval augmented generation"], ...}
_BUILTIN_ALIASES: dict[str, list[str]] = {
    "rag": ["retrieval augmented generation", "retrieval-augmented generation"],
    "llm": ["large language model", "large language models", "llms", "gpt", "openai", "chatgpt"],
    "ml": ["machine learning"],
    "ai": ["artificial intelligence"],
    "nlp": ["natural language processing", "natural language"],
    "cv": ["computer vision"],
    "azure openai": ["openai", "gpt"],
    "azure ai foundry": ["azure ai studio", "azure openai", "azure ai services", "azure ai"],
    "ai foundry": ["azure ai foundry", "azure ai studio"],
    "enterprise search": ["azure ai search", "azure cognitive search", "knowledge retrieval", "knowledge assistant", "semantic search"],
    "sharepoint online": ["sharepoint", "spo"],
    "power apps": ["powerapps", "power app"],
    "power automate": ["microsoft flow", "power automation"],
    "power bi": ["powerbi"],
    "dotnet": ["asp net", "net core", "c#"],
    "m365": ["microsoft 365", "office 365", "o365"],
    "microsoft 365": ["m365", "office 365", "o365"],
    "k8s": ["kubernetes"],
    "js": ["javascript"],
    "ts": ["typescript"],
}
_STOP = {
    "and", "or", "the", "a", "an", "of", "to", "in", "for", "with", "on", "using", "experience", "knowledge",
    "strong", "skills", "skill", "hands", "based", "development", "platform", "tools", "tool", "solutions",
    "services", "service", "technologies", "technology", "microsoft",
    "evaluation", "experimentation", "techniques", "fundamentals", "concepts", "practices", "principles",
    "administration", "administrator", "methods", "approach", "frameworks", "framework", "general", "understanding", "familiarity", "proficiency",
}


def _load_aliases() -> dict[str, list[str]]:
    aliases = {k: list(v) for k, v in _BUILTIN_ALIASES.items()}
    path = Path(__file__).resolve().parent.parent.parent / "config" / "skill_aliases.json"
    try:
        if path.exists():
            for k, v in json.loads(path.read_text(encoding="utf-8")).items():
                aliases.setdefault(k.lower(), []).extend(x.lower() for x in v)
    except Exception:
        pass
    return aliases


ALIASES = _load_aliases()


@dataclass
class RequirementVerdict:
    skill: str
    importance: str = "must"
    verdict: str = "none"
    evidence_quote: str = ""
    grounded: bool = False
    share: float = 1.0  # fraction of the original requirement's weight (split compounds share it)
    source: str = ""  # why the final verdict was chosen (debug / UI)
    group: str = ""  # alternatives from one requirement ("A, B or C")
    any_of: bool = False  # True: the group is satisfied by its best member


@dataclass
class ScoreOutcome:
    score: int
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    base: int = 0
    cap: int = 100


def normalize(text: str) -> str:
    """Lowercase, drop punctuation (keeping + # . for c++/c#/.net), collapse whitespace."""
    t = re.sub(r"[^\w\s\+#\.]", " ", (text or "").lower())
    t = re.sub(r"(?<!\w)\.|\.(?!\w)", " ", t)
    return " " + re.sub(r"\s+", " ", t).strip() + " "


def phrase_in(phrase: str, haystack_norm: str) -> bool:
    """Whole-word(-ish) phrase match, tolerant to a plural 's'."""
    p = normalize(phrase).strip()
    if not p:
        return False
    return f" {p} " in haystack_norm or f" {p}s " in haystack_norm


def _variants(skill: str) -> list[str]:
    key = normalize(skill).strip()
    core = " ".join(_tokens(skill))  # filler words dropped: "machine learning evaluation" -> "machine learning"
    out = [key] + ([core] if core and core != key else [])
    out += ALIASES.get(key, []) + (ALIASES.get(core, []) if core != key else [])
    # reverse lookup: skill is itself an alias of a canonical key
    for canon, alts in ALIASES.items():
        if key in alts:
            out.append(canon)
            out += alts
    return list(dict.fromkeys(out))


def has_signal(skill: str) -> bool:
    """False for fragments made only of filler words (e.g. experimentation, best practices)."""
    return bool(_tokens(skill))


def _tokens(skill: str) -> list[str]:
    return [t for t in normalize(skill).split() if t not in _STOP and len(t) >= 2]


def token_coverage(skill: str, ev_norm: str) -> tuple[float, bool]:
    """(fraction of significant skill tokens present in the evidence, whole phrase/alias present)."""
    for v in _variants(skill):
        if phrase_in(v, ev_norm):
            return 1.0, True
    toks = _tokens(skill)
    if not toks:
        return 0.0, False
    hit = 0
    for t in toks:
        if phrase_in(t, ev_norm) or any(phrase_in(a, ev_norm) for a in ALIASES.get(t, [])):
            hit += 1
    return hit / len(toks), False


def ground_verdict(v: RequirementVerdict, evidence_text: str, quote_text: str = "") -> RequirementVerdict:
    """Decide the final verdict from the evidence itself, using the LLM label as a hint.

    evidence_text: full text of the chunks retrieved for THIS requirement (decides upgrades).
    quote_text:    wider text (incl. role-level chunks) used only to validate the LLM's quote.
    """
    ev_norm = normalize(evidence_text)
    cov, phrase = token_coverage(v.skill, ev_norm)
    quote_norm = normalize(v.evidence_quote).strip()
    quote_ok = len(quote_norm) >= 8 and f" {quote_norm} " in normalize(quote_text or evidence_text)
    llm = v.verdict if v.verdict in ("covered", "partial", "none") else "none"

    n_tok = len(_tokens(v.skill))
    if phrase:
        verdict, why = "covered", "skill (or alias) stated in KB"
    elif cov >= 1.0:
        if n_tok == 1 or llm == "covered":
            verdict, why = "covered", "all terms present in KB"
        else:
            verdict, why = "partial", "all terms present but not as one capability"
    elif llm == "covered" and quote_ok and cov >= 0.67:
        verdict, why = "covered", "LLM + verified quote"
    elif cov >= 0.67:
        verdict, why = "partial", "most terms present in KB"
    else:
        verdict, why = "none", "no KB support"
    v.verdict, v.source = verdict, why
    v.grounded = verdict != "none"
    return v


def compute_score(verdicts: list[RequirementVerdict], role_fit: str = "partial") -> ScoreOutcome:
    total_w = 0.0
    earned = 0.0
    matched: list[str] = []
    missing: list[str] = []
    done_groups: set[str] = set()
    for v in verdicts:
        w = IMPORTANCE_WEIGHT.get(v.importance, 1.0)
        if v.any_of and v.group:
            if v.group in done_groups:
                continue
            done_groups.add(v.group)
            members = [m for m in verdicts if m.group == v.group]
            best = max(VERDICT_CREDIT.get(m.verdict, 0.0) for m in members)
            total_w += w
            earned += w * best
            hit = [m for m in members if VERDICT_CREDIT.get(m.verdict, 0.0) > 0]
            if hit:
                for m in hit:
                    matched.append(m.skill if m.verdict == "covered" else f"{m.skill} (partial)")
            else:
                missing.extend(m.skill for m in members)
            continue
        w *= v.share
        total_w += w
        earned += w * VERDICT_CREDIT.get(v.verdict, 0.0)
        if v.verdict == "covered":
            matched.append(v.skill)
        elif v.verdict == "partial":
            matched.append(f"{v.skill} (partial)")
        else:
            missing.append(v.skill)
    base = int(round(100 * earned / total_w)) if total_w else 0
    cap = ROLE_FIT_CAP.get(role_fit, ROLE_FIT_CAP["partial"])
    return ScoreOutcome(score=min(base, cap), matched=matched, missing=missing, base=base, cap=cap)
