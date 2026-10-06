"""
Eligibility Filter
==================
Rejects postings that make a country-specific eligibility condition MANDATORY - citizenship,
permanent residency / green card, work authorization or a specific visa/work permit, security
clearance, country residency, or export-control ("U.S. person") status - for ANY country.

We are an offshore IT-services company, so a posting that only a citizen / resident / cleared
person of one country may fill is not a lead we can serve.

Deliberately conservative: it only rejects when the requirement is explicit.
  * "must be a U.S. citizen", "USC/GC only", "active TS/SCI", "no sponsorship available"      -> reject
  * "clearance is a plus", "citizenship preferred", "visa sponsorship available",
    "regardless of citizenship", a bare unqualified mention                                      -> keep
  * anything under a "Preferred / Nice to have / Bonus" heading                                  -> keep

Pure rules (no LLM, no network): fast, free and reproducible. Each decision carries the matched
sentence so it can be audited in the dashboard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.utils.logger import logger

# ------------------------------------------------------------------ vocabulary
_COUNTRIES = (
    r"(?-i:U\.S\.A\.?|U\.S\.|USA|US|U\.K\.|UK|EU|E\.U\.|EEA|UAE|GCC)|"
    r"united\s+states(?:\s+of\s+america)?|america|united\s+kingdom|great\s+britain|britain|england|scotland|wales|"
    r"northern\s+ireland|canada|australia|new\s+zealand|ireland|germany|france|netherlands|belgium|spain|italy|"
    r"portugal|switzerland|austria|sweden|norway|denmark|finland|poland|czech(?:ia|\s+republic)|romania|bulgaria|"
    r"hungary|greece|luxembourg|singapore|hong\s+kong|japan|china|south\s+korea|korea|taiwan|india|pakistan|"
    r"bangladesh|sri\s+lanka|philippines|indonesia|malaysia|thailand|vietnam|israel|saudi\s+arabia|"
    r"united\s+arab\s+emirates|qatar|kuwait|bahrain|oman|egypt|south\s+africa|nigeria|kenya|ghana|brazil|argentina|"
    r"mexico|chile|colombia|peru|turkey|t[uü]rkiye|russia|ukraine|european\s+union|the\s+eu|the\s+eea"
)
_DEMONYMS = (
    r"(?-i:U\.S\.|US|U\.K\.|UK|EU)|american|british|canadian|australian|new\s+zealand(?:er)?|irish|german|french|"
    r"dutch|belgian|spanish|italian|portuguese|swiss|austrian|swedish|norwegian|danish|finnish|polish|czech|"
    r"romanian|hungarian|greek|singaporean|japanese|chinese|korean|indian|israeli|emirati|saudi|qatari|"
    r"south\s+african|nigerian|brazilian|mexican|turkish|russian|ukrainian|european|uk|us"
)
C = rf"(?:{_COUNTRIES})"
D = rf"(?:{_DEMONYMS})"

# ------------------------------------------------------------------ restriction patterns
# (category, label, regex, inherent)  inherent=True: the wording is exclusionary on its own;
# inherent=False: also needs a mandatory word (must/required/only/...) in the same sentence.
_I = re.IGNORECASE
_PATTERNS: list[tuple[str, str, re.Pattern, bool]] = []


def _p(category: str, label: str, pattern: str, inherent: bool, flags: int = _I) -> None:
    _PATTERNS.append((category, label, re.compile(pattern, flags), inherent))


# --- citizenship
_p("citizenship", "citizenship", rf"\b{D}\s+(?:citizens?(?:hip)?|nationals?|passport)\b", False)
_p("citizenship", "citizenship", rf"\bcitizens?(?:hip)?\s+(?:of|in)\s+(?:the\s+)?{C}", False)
_p("citizenship", "citizenship", r"\b(?:must|need\s+to|needs\s+to|required\s+to|have\s+to|should)\s+(?:be|hold|have|possess)\s+(?:a\s+|an\s+)?(?:valid\s+)?(?:[\w.\-]+\s+){0,2}?citizen(?:ship|s)?\b", True)
_p("citizenship", "citizenship", r"\bcitizenship\s+(?:status\s+)?(?:is\s+)?(?:required|mandatory|a\s+must|necessary|needed)\b", True)
_p("citizenship", "citizenship", r"\b(?:citizens?|nationals?)\s+only\b", True)
_p("citizenship", "citizenship", r"\bonly\s+(?:[\w.\-]+\s+){0,3}?(?:citizens?|nationals?)\b", True)
_p("citizenship", "citizenship", r"\bcitizen(?:s|ship)?\s+(?:or|/|and)\s+(?:permanent\s+residents?|green\s*card|PR\b)", False)

# --- permanent residency / green card / local status jargon
_p("permanent residency", "permanent residency / green card", r"\bgreen\s*card\b", False)
_p("permanent residency", "permanent residency", r"\b(?:lawful\s+)?permanent\s+residen(?:t|ts|cy|ce)\b", False)
_p("permanent residency", "permanent residency", r"\bPR\s+(?:holders?|status|card)\b", False, 0)
_p("permanent residency", "settled status / ILR", r"\b(?:settled\s+status|indefinite\s+leave\s+to\s+remain)\b", False)
_p("permanent residency", "USC/GC status", r"(?<![\w])(?:USC|GC[- ]?EAD|H-?4[- ]?EAD|GC)(?![\w])(?:\s*(?:/|,|or|and|&)\s*(?:USC|GC[- ]?EAD|H-?4[- ]?EAD|GC|TN|Green\s*Card))*", True, 0)

# --- work authorization / right to work
_p("work authorization", "work authorization", rf"\b(?:legally\s+|lawfully\s+|currently\s+)?(?:authori[sz]ed|eligible|permitted|allowed|entitled|legal(?:ly)?\s+able)\s+to\s+work\s+(?:in|within|for\s+(?:any\s+)?employer\s+in)\s+(?:the\s+)?{C}", True)
_p("work authorization", "right to work", rf"\bright\s+to\s+work\s+(?:in|within)\s+(?:the\s+)?{C}", True)
_p("work authorization", "work authorization", r"\b(?:valid|current|existing|proof\s+of|proper)\s+(?:\w+\s+)?work\s+(?:authori[sz]ation|permit|eligibility|visa)\b", True)
_p("work authorization", "work authorization", r"\bwork\s+(?:authori[sz]ation|permit|eligibility)\b", False)
_p("work authorization", "employment authorization", r"\bemployment\s+(?:authori[sz]ation|eligibility\s+verification)\b", False)
_p("work authorization", "no sponsorship", r"\b(?:no|not|cannot|can't|can\s*not|unable|won't|will\s+not|does\s+not|do\s+not|doesn't|don't|without|never|not\s+able)\b[^.\n;]{0,45}?\bsponsor\w*\b", True)
_p("work authorization", "no sponsorship", r"\bsponsorship\s+(?:is\s+)?(?:not|un)\s*(?:available|offered|provided|possible)\b", True)
_p("work authorization", "no sponsorship", r"\b(?:not|never)\b[^.\n;]{0,70}?\brequire[^.\n;]{0,40}?\bsponsor", True)
_p("work authorization", "no sponsorship", r"\bsponsorship\b[^.\n;]{0,30}\b(?:not\s+(?:available|offered|provided)|unavailable)\b", True)

# --- specific visa / permit
_p("visa", "visa restriction", r"\b(?:no|not|without|exclud\w+)\b[^.\n;]{0,25}?\b(?:H-?1B|OPT|CPT|F-?1|L-?1|TN|third[- ]party\s+visa|visa\s+holders?|visa\s+transfers?)\b", True)
_p("visa", "visa restriction", r"\b(?:H-?1B|OPT|CPT|F-?1|L-?1)\b[^.\n;]{0,20}?\b(?:not|cannot|can't)\b[^.\n;]{0,15}?\b(?:accepted|considered|supported|eligible)\b", True)
_p("visa", "visa required", r"\b(?:valid|current)\s+(?:[\w\-]+\s+){0,3}?visa\b", False)
_p("visa", "visa required", r"\bvisa\s+(?:status\s+)?(?:is\s+)?(?:required|mandatory)\b", True)
_p("visa", "visa required", r"\b(?:must|need\s+to|required\s+to)\s+(?:have|hold|possess|obtain)\b[^.\n;]{0,40}?\b(?:visa|work\s+permit)\b", True)
_p("visa", "visa required", r"\b(?:skilled\s+worker|tier\s*[1-5]|blue\s+card|E-?3|H-?1B1)\s+(?:visa|permit)?\b[^.\n;]{0,25}\b(?:required|only|must)\b", True)

# --- export control / "U.S. person"
_p("export control", "U.S. person (ITAR/EAR)", r"\b(?:U\.?S\.?|United\s+States)\s+persons?\b", False, 0)
_p("export control", "export-control citizenship", r"\b(?:ITAR|EAR|export[- ]control(?:led)?)\b[^.\n]{0,100}?\b(?:citizen|U\.?S\.?\s+person|national|permanent\s+resident)", True)

# --- security clearance (US/UK/CA/AU/EU variants)
_p("security clearance", "security clearance", r"\b(?:security|government|DoD|federal|national)\s+clearance\b", False)
_p("security clearance", "security clearance", r"\b(?:TS\s*/\s*SCI|TS-SCI|top[- ]secret(?:\s+clearance)?|secret\s+clearance|public\s+trust|full[- ]scope\s+poly(?:graph)?|counter[- ]intelligence\s+poly(?:graph)?|CI\s+poly(?:graph)?|polygraph|Q\s+clearance|L\s+clearance)\b", False)
_p("security clearance", "security clearance", r"\b(?:SC|DV|eDV|CTC|BPSS|NPPV\s*[123]?|NV\s*[12])\s+(?:clearance|cleared|vetting|level|security)\b", False, 0)
_p("security clearance", "security clearance", r"\b(?:security\s+vetting|reliability\s+status|enhanced\s+reliability|secret\s+level|baseline\s+clearance|AGSVA)\b", False)
_p("security clearance", "security clearance", r"\b(?:active|current|valid|existing|up[- ]to[- ]date)\s+(?:[\w/\-]+\s+){0,2}?(?:clearance|secret|top[- ]secret)\b", True)
_p("security clearance", "security clearance", r"\b(?:able|ability|eligible|eligibility|must|need\s+to|required\s+to)\s+(?:to\s+)?(?:obtain|hold|maintain|get|be\s+granted|qualify\s+for)\b[^.\n;]{0,40}?\bclearance\b", True)
_p("security clearance", "security clearance", r"\bclearance\b[^.\n;]{0,25}\b(?:is\s+)?(?:required|mandatory|a\s+must|necessary)\b", True)

# --- country residency / location-locked
_p("residency", "country residency", rf"\b(?:must|need\s+to|needs\s+to|required\s+to|have\s+to)\s+(?:currently\s+)?(?:reside|live|be\s+(?:located|based|resident|residing|living|physically\s+located))\s+(?:in|within)\s+(?:the\s+)?{C}", True)
_p("residency", "country residency", rf"\b{C}\s+(?:residents?|based\s+(?:candidates|applicants)|candidates|applicants|locals?)\s+only\b", True)
_p("residency", "country residency", rf"\bonly\s+(?:candidates|applicants|people|those)\s+(?:who\s+)?(?:are\s+)?(?:currently\s+)?(?:located|residing|living|based|resident)\s+in\s+(?:the\s+)?{C}", True)
_p("residency", "country residency", rf"\bmust\s+be\s+(?:a\s+)?(?:legal\s+)?(?:{C}|{D})\s+resident\b", True)
_p("residency", "country residency", rf"\bresident\s+of\s+(?:the\s+)?{C}\b[^.\n;]{{0,20}}\b(?:required|mandatory|only)\b", True)
_p("residency", "country residency", rf"\b(?:remote|work\s+from\s+home|wfh)\b[^.\n;]{{0,12}}\b{C}\s*[-–]?\s*(?:only|based\s+only)\b", True)
_p("residency", "country residency", rf"\b(?:open|available|limited|restricted)\s+(?:to|for)\s+{C}\s+(?:residents?|candidates|applicants)\s+only\b", True)

_p("residency", "country residency", rf"(?<![\w]){C}\s*[-–]?\s*only\b", True)
# contracts / contractors / engagements that are limited to people based in one country
_p("residency", "country-based contract", rf"\b(?:contractors?|freelancers?|consultants?|contract|assignment|engagement|position|role)\b[^.\n;]{{0,40}}?\b(?:based|located|resident|residing)\s+(?:in|within)\s+(?:the\s+)?{C}", True)
_p("residency", "country-based contract", rf"(?<![\w])(?:{C}|{D})[- ]based\s+(?:candidates?|applicants?|contract\w*|freelanc\w*|consultants?|contractors?|resources?|talent|professionals?|developers?|engineers?|workers?)\b", True)

# ------------------------------------------------------------------ context markers
_MANDATORY = re.compile(
    r"\b(?:must|required|requires?|requirement|mandatory|only|need\s+to|needs\s+to|have\s+to|essential|"
    r"eligib\w*|cannot|can't|unable|shall|necessary|prerequisite|to\s+be\s+considered|not\s+(?:able|eligible)|"
    r"no\s+exceptions|will\s+be\s+required)\b", _I)

_OPTIONAL = re.compile(
    r"\b(?:preferred|prefer|a\s+plus|nice[- ]to[- ]have|desirable|desired|bonus|advantage|an\s+asset|ideally|ideal|"
    r"(?:is|are)\s+not\s+(?:required|necessary|mandatory|needed)|not\s+(?:required|necessary|mandatory|needed)|"
    r"no\s+[\w\s/]{0,25}?\s+(?:is\s+)?required|optional|beneficial|helpful|does\s+not\s+require|do\s+not\s+require|"
    r"need\s+not|may\s+(?:be\s+)?(?:required|considered)|can\s+be\s+(?:obtained|arranged|sponsored)|"
    r"(?:will|can|do|does|may|would|are\s+able\s+to|is\s+able\s+to)\s+(?:also\s+)?(?:sponsor|assist\s+with\s+(?:visa|relocation))|"
    r"sponsorship\s+(?:is\s+)?(?:available|provided|offered|possible|supported)|"
    r"(?:visa|work\s+permit|immigration)\s+(?:sponsorship|support)\s+(?:is\s+)?(?:available|provided|offered|possible|supported)|"
    r"(?:able|willing|happy|open)\s+to\s+sponsor|sponsors?\s+(?:visas?|work\s+permits?)|"
    r"(?:green\s*card|GC|visa|immigration|work\s+permit)\s+(?:assistance|processing|support|help|services?)|"
    r"(?:assist|support|help|sponsor)\w*\s+(?:you\s+)?(?:with\s+|in\s+|for\s+)?(?:your\s+)?(?:green\s*card|visa|immigration|work\s+permit|relocation)|"
    r"if\s+required|where\s+required|as\s+needed|"
    r"all\s+(?:visa|work\s+authori[sz]ations?|work\s+permits?)|any\s+(?:visa|work\s+authori[sz]ation|work\s+permit)|"
    r"open\s+to\s+(?:all|any)|transfers?\s+(?:accepted|welcome|ok)|"
    r"(?:regardless|irrespective)\s+of|without\s+regard|does\s+not\s+discriminate|equal\s+opportunity|"
    r"(?:can|will)\s+be\s+(?:obtained|processed|arranged)|apply\s+for\s+(?:the\s+)?clearance|"
    r"(?:we|company|employer)\s+(?:will\s+)?(?:obtain|arrange|process)\w*\s+(?:the\s+)?clearance)\b", _I)

# Statements that clearly OFFER sponsorship: they neutralise work-authorization / visa restrictions
# (a candidate who needs a visa is welcome), but never citizenship / clearance / residency ones.
_SPONSOR_POSITIVE = re.compile(
    r"\b(?:(?:will|can|do|does|may|would|able\s+to|willing\s+to|happy\s+to|open\s+to)\s+(?:also\s+)?sponsor|"
    r"(?:visa|work\s+permit|immigration)?\s*sponsorship\s+(?:is\s+)?(?:available|provided|offered|possible)|"
    r"sponsors?\s+(?:work\s+)?visas?|(?:green\s*card|GC|visa|immigration|work\s+permit)\s+(?:assistance|processing|support|help)|visa\s+support\s+(?:is\s+)?(?:available|provided)|h-?1b\s+(?:transfers?\s+)?(?:sponsorship\s+)?(?:available|accepted|welcome|ok))\b",
    _I,
)
_SPONSOR_NEGATIVE = re.compile(
    r"\b(?:no|not|cannot|can't|unable|won't|never|without)\b[^.\n;]{0,45}?\bsponsor|"
    r"\bsponsorship\s+(?:is\s+)?(?:not|un)\s*(?:available|offered|provided|possible)|"
    r"\b(?:not|never)\b[^.\n;]{0,70}?\brequire[^.\n;]{0,40}?\bsponsor", _I)

_SOFT_CATEGORIES_NEUTRALISED_BY_SPONSORSHIP = {"work authorization", "visa"}

_OPT_HEADING = re.compile(
    r"^\s*(?:#+\s*)?(?:preferred|nice[- ]to[- ]haves?|bonus(?:\s+points)?|desired|desirable|plus(?:es)?|good\s+to\s+have|"
    r"additional|optional)(?:\s+(?:qualifications|skills|requirements|experience|attributes))?\s*:?\s*$", _I)
_REQ_HEADING = re.compile(
    r"^\s*(?:#+\s*)?(?:requirements?|qualifications?|minimum(?:\s+qualifications)?|basic(?:\s+qualifications)?|required(?:\s+\w+)?|"
    r"responsibilities|key\s+responsibilities|what\s+you(?:'|’)?ll\s+(?:need|do)|about\s+(?:you|the\s+role)|must[- ]haves?|"
    r"skills|who\s+you\s+are|eligibility)\s*:?\s*$", _I)

_CATEGORY_PRIORITY = ["citizenship", "security clearance", "permanent residency", "export control",
                      "work authorization", "visa", "residency"]
_BLOCK_TAG_RE = re.compile(r"</?(?:p|li|ul|ol|div|br|h[1-6]|tr|td|table|section)[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+|(?<=[a-z]{2}[.!?])(?=[A-Z])|\n+|[•·▪●■]\s*|\s+-\s+(?=[A-Z])")


@dataclass
class EligibilityVerdict:
    restricted: bool = False
    category: str = ""
    label: str = ""
    snippet: str = ""
    hits: list[tuple[str, str]] = field(default_factory=list)  # (category, snippet) of every mandatory hit

    @property
    def short_reason(self) -> str:
        """Short plain-language reason for the Reject Reason column."""
        if not self.restricted:
            return ""
        phrase = {
            "citizenship": "Citizenship required",
            "permanent residency": "Permanent residency / green card required",
            "work authorization": "Local work authorization required (no sponsorship)",
            "visa": "Specific visa required",
            "export control": "U.S. person / export-control status required",
            "security clearance": "Security clearance required",
            "residency": "Must reside in a specific country",
        }.get(self.category, "Eligibility restriction")
        quote = re.sub(r"\s+", " ", self.snippet).strip("… ")
        if len(quote) > 60:
            quote = quote[:57].rstrip() + "..."
        return f'{phrase}: "{quote}"' if quote else phrase

    @property
    def reason(self) -> str:
        if not self.restricted:
            return ""
        return f"Eligibility restriction ({self.label}): \"{self.snippet}\""


_INLINE_REQ_HEADING = re.compile(
    r"^\s*(?:#+\s*)?(?:minimum|basic|required|mandatory|essential)(?:\s+(?:qualifications|requirements|skills))?\s*:\s*(?P<rest>.*)$", _I)


_BULLET_START = re.compile(r"^\s*[•·▪●■\-\*\d]")


def _is_section_heading(lines: list[str], idx: int) -> bool:
    """A short, unbulleted line on its own (blank line before it), e.g. "Engagement details" - it ends a
    Preferred section. Items of a plain list are not preceded by a blank line, so they are not mistaken for headings."""
    raw = lines[idx]
    text = raw.strip().rstrip(":")
    if not text or _BULLET_START.match(raw) or text[-1] in ".,;!?":
        return False
    if idx > 0 and lines[idx - 1].strip():
        return False
    words = text.split()
    return 1 <= len(words) <= 5 and text[0].isupper()


def _segments(text: str):
    """Yield (segment, in_optional_section, in_requirements_section) while tracking section headings.

    Under a Requirements / Minimum Qualifications heading even a bare "U.S. citizenship" bullet is a
    requirement; under Preferred / Nice-to-have the same bullet is optional."""
    in_opt = False
    in_req = False
    all_lines = text.splitlines()
    for line_idx, raw_line in enumerate(all_lines):
        line = raw_line.strip()
        if not line:
            continue
        if len(line) <= 70:
            if _OPT_HEADING.match(line):
                in_opt, in_req = True, False
                continue
            if _REQ_HEADING.match(line):
                in_opt, in_req = False, True
                continue
            if in_opt and _is_section_heading(all_lines, line_idx):  # e.g. "Engagement details" after "Preferred qualifications"
                in_opt = False
                continue
        inline = _INLINE_REQ_HEADING.match(line)
        if inline:  # "Minimum Qualifications: * U.S. citizenship * BA/BS ..." on one line
            in_opt, in_req = False, True
            line = inline.group("rest")
        for seg in _SPLIT_RE.split(line):
            seg = (seg or "").strip(" 	-–—•*")
            if len(seg) >= 6:
                yield seg, in_opt, in_req


def _snippet(seg: str, m: re.Match) -> str:
    start = max(0, m.start() - 40)
    end = min(len(seg), m.end() + 40)
    while start > 0 and start < m.start() and not seg[start - 1].isspace():
        start += 1  # don't begin in the middle of a word
    while end < len(seg) and end > m.end() and not seg[end].isspace():
        end -= 1  # ... or end in the middle of one
    out = seg[start:end].strip()
    return ("…" if start > 0 else "") + out + ("…" if end < len(seg) else "")


def check_text(text: str, title: str = "") -> EligibilityVerdict:
    """Decide whether the posting makes a country-specific eligibility condition mandatory."""
    body = _TAG_RE.sub("", _BLOCK_TAG_RE.sub("\n", f"{title}\n{text or ''}"))  # block tags break lines; inline tags vanish
    if not body.strip():
        return EligibilityVerdict()
    # Dotted abbreviations must not look like sentence ends ("U.S. citizen" would split after "U.S.")
    body = re.sub(r"\bU\.\s?S\.\s?A\b\.?", "USA", body)
    body = re.sub(r"\bU\.\s?S\b\.?", "US", body)
    body = re.sub(r"\bU\.\s?K\b\.?", "UK", body)
    body = re.sub(r"\bE\.\s?U\b\.?", "EU", body)

    sponsorship_offered = bool(_SPONSOR_POSITIVE.search(body)) and not _SPONSOR_NEGATIVE.search(body)
    hits: list[tuple[str, str, str]] = []  # (category, label, snippet)

    for seg, in_opt, in_req in _segments(body):
        seg_optional = bool(_OPTIONAL.search(seg))
        seg_mandatory = bool(_MANDATORY.search(seg)) or in_req  # inside a requirements section every line is required
        for category, label, rx, inherent in _PATTERNS:
            m = rx.search(seg)
            if not m:
                continue
            negative_sponsorship = label == "no sponsorship"
            if negative_sponsorship and re.search(r"export\s+licen[cs]e|licen[cs]e\s+sponsor", seg, _I):
                continue  # sponsoring an export licence is not a visa/work-authorization statement
            # Optional section / softening wording neutralises a restriction ... except "no sponsorship",
            # which states a hard company limit whatever the wording around it.
            if not negative_sponsorship and (in_opt or seg_optional):
                continue
            if negative_sponsorship and _OPTIONAL.search(seg) and re.search(r"regardless|without\s+regard|equal\s+opportunity|discriminat", seg, _I):
                continue
            if not inherent and not seg_mandatory:
                continue  # a bare mention is not an explicit requirement
            if category in _SOFT_CATEGORIES_NEUTRALISED_BY_SPONSORSHIP and sponsorship_offered and not negative_sponsorship:
                continue
            hits.append((category, label, _snippet(seg, m)))

    if not hits:
        return EligibilityVerdict()

    hits.sort(key=lambda h: _CATEGORY_PRIORITY.index(h[0]) if h[0] in _CATEGORY_PRIORITY else 99)
    category, label, snippet = hits[0]
    return EligibilityVerdict(
        restricted=True, category=category, label=label, snippet=snippet,
        hits=[(c, s) for c, _, s in hits],
    )


def check_job(job) -> EligibilityVerdict:
    return check_text(getattr(job, "job_description", "") or "", getattr(job, "job_title", "") or "")


def apply_eligibility(job) -> bool:
    """If `job` has a mandatory country-specific eligibility restriction, mark it Rejected and return True.
    Never raises (a rules bug must not stop a scrape)."""
    try:
        verdict = check_job(job)
    except Exception as exc:
        logger.error("Eligibility check failed for '{}': {}", getattr(job, "job_title", "?"), exc)
        return False
    if not verdict.restricted:
        return False
    job.lead_class = "Rejected"
    job.lead_score = 0
    job.lead_category = "Eligibility restriction"
    job.lead_reason = verdict.reason
    job.reject_reason = verdict.short_reason
    job.engagement_type = "eligibility_restricted"
    return True
