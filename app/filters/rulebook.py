"""
Desire Infoweb job-filtering rulebook (deterministic engine)
============================================================
Implements the written rulebook (sections A-I) with rule IDs. Every decision is one of
RELEVANT / NOT RELEVANT / MAYBE, with ONE short reason and the rule that triggered.

  * D1-D3 and B4 reuse app.filters.eligibility_filter (citizenship / green card, clearance, work
    authorization, country residency) - already built and tested, so they are kept as they are.
  * New here: B1-B3/B5, C1-C5, D4-D6, E1-E5, F1-F2, G1-G4 (NOT RELEVANT) and H1-H8 / I2 (MAYBE).
  * Rules B-G always override a skills match (I3): a NOT RELEVANT hit rejects the lead before any LLM call.

Same philosophy as the eligibility filter: only EXPLICIT wording rejects. Wording that is softened
("preferred", "a plus", "optional", "not required", "no relocation needed"), anything under a
"Preferred / Nice to have" heading, and sponsorship/assistance offers never reject.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.filters import eligibility_filter as elig
from app.utils.logger import logger

NOT_RELEVANT, MAYBE, RELEVANT = "NOT RELEVANT", "MAYBE", "RELEVANT"

# Section titles used in short reasons / the category column
RULE_GROUP = {
    "A": "Must-pass", "B": "Location rule", "C": "Employment-type rule", "D": "Eligibility restriction",
    "E": "Vendor policy", "F": "Language rule", "G": "Role-type rule", "H": "Manual review", "I": "Housekeeping",
}

# Order in which the PRIMARY reason is chosen when several NOT RELEVANT rules fire
_PRIORITY = ["D1", "D2", "E1", "E2", "E3", "E4", "D3", "D4", "D5", "D6", "E5", "G1", "G2", "G3", "G4", "B4", "C1", "C5",
             "C2", "C4", "B1", "B2", "B3", "B5", "F1"]

_I = re.IGNORECASE

_US_STATES = (
    "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|"
    "Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|"
    "Montana|Nebraska|Nevada|New\\s+Hampshire|New\\s+Jersey|New\\s+Mexico|New\\s+York|North\\s+Carolina|North\\s+Dakota|"
    "Ohio|Oklahoma|Oregon|Pennsylvania|Rhode\\s+Island|South\\s+Carolina|South\\s+Dakota|Tennessee|Texas|Utah|Vermont|"
    "Virginia|Washington|West\\s+Virginia|Wisconsin|Wyoming|Ontario|Quebec|British\\s+Columbia|Alberta|Manitoba|"
    "Nova\\s+Scotia|Saskatchewan|Queensland|Victoria|New\\s+South\\s+Wales|Bavaria|Catalonia|Scotland|Wales|England"
)
_AGENCIES = (
    "VDOT|[A-Z]{2}DOT|DOT|DoD|DHS|DOJ|VA|IRS|CMS|HHS|FEMA|NASA|USDA|DOE|DOL|EPA|FAA|FDA|NIH|CDC|SSA|USCIS|GSA|OPM|DISA|"
    "USPS|TSA|CBP|ICE|DMV|HUD|DOC|NOAA|USGS|BLM|NGA|NSA|CIA|FBI|DEA|ATF|SEC|FDIC|FCC|FTC|USAF|USN|Army|Navy|Air\\s+Force|"
    "Marine\\s+Corps|Department\\s+of\\s+[A-Z]\\w+|State\\s+of\\s+[A-Z]\\w+|Commonwealth\\s+of\\s+[A-Z]\\w+|"
    "County\\s+of\\s+[A-Z]\\w+|City\\s+of\\s+[A-Z]\\w+"
)
_LANGS = (
    "German|French|Spanish|Cantonese|Mandarin|Chinese|Japanese|Korean|Arabic|Portuguese|Italian|Russian|Hindi|Dutch|"
    "Polish|Turkish|Hebrew|Vietnamese|Thai|Tagalog|Swedish|Norwegian|Danish|Finnish|Greek|Czech|Hungarian|Romanian|"
    "Ukrainian|Bengali|Urdu|Tamil|Punjabi|Indonesian|Malay|Farsi|Persian"
)

# (rule, decision, label, regex, inherent, ignore_optional)
_PATTERNS: list[tuple[str, str, str, re.Pattern, bool, bool]] = []


def _r(rule: str, decision: str, label: str, pattern: str, inherent: bool = True, ignore_optional: bool = False,
       flags: int = _I) -> None:
    _PATTERNS.append((rule, decision, label, re.compile(pattern, flags), inherent, ignore_optional))


# ---------------------------------------------------------------- B: location
_r("B1", NOT_RELEVANT, "hybrid / on-site / in-office",
   r"\bhybrid\s+(?:work|role|position|schedule|model|arrangement|opportunity|environment|setting|remote|basis|office|working)\b")
_r("B1", NOT_RELEVANT, "hybrid / on-site / in-office", r"\b(?:is|are|be|will\s+be)\s+(?:a\s+)?(?:fully\s+)?hybrid\b")
_r("B1", NOT_RELEVANT, "hybrid / on-site / in-office", r"(?:^|[-–(,|]\s*)hybrid\s*\)?\s*$")
_r("B1", NOT_RELEVANT, "hybrid / on-site / in-office", r"\bhybrid\s*[-–(:]\s*\d")
_r("B1", NOT_RELEVANT, "days in office", r"\b(?:\d|one|two|three|four|five)\s+days?\s+(?:per\s+week\s+|a\s+week\s+|each\s+week\s+)?(?:in|at|on)[- ]?(?:the\s+)?(?:office|site)\b")
_r("B1", NOT_RELEVANT, "days in office", r"\b(?:in|at)\s+the\s+office\s+(?:\d|one|two|three|four|five)\s+days?\b")
_r("B1", NOT_RELEVANT, "on-site required", r"\b(?:on-?site|onsite|in-?office|in[- ]person)\b[^.\n;]{0,25}\b(?:required|mandatory|only|expected|presence|attendance|position|role|days?)\b")
_r("B1", NOT_RELEVANT, "on-site required", r"\b(?:position|role|job|work|this)\s+(?:is|will\s+be)\s+(?:fully\s+)?(?:on-?site|onsite|in-?office|office[- ]based)\b")
_r("B1", NOT_RELEVANT, "on-site required", r"\b(?:on-?site|onsite)\s+(?:position|role|work|presence|only)\b")
_r("B1", NOT_RELEVANT, "return to office", r"\breturn[- ]to[- ]office\b")
_r("B1", NOT_RELEVANT, "return to office", r"\bRTO\b", True, False, 0)
_r("B1", NOT_RELEVANT, "on-site (title)", r"[-–(|]\s*(?:on-?site|onsite|in-?office)\s*\)?\s*$")

_r("B2", NOT_RELEVANT, "relocation required", r"\brelocat(?:e|ion|ing)\b[^.\n;]{0,30}\b(?:is\s+)?(?:required|mandatory|necessary|a\s+must)\b")
_r("B2", NOT_RELEVANT, "relocation required", r"\b(?:must|will\s+need\s+to|required\s+to|have\s+to)\s+(?:be\s+(?:willing|able)\s+to\s+)?relocate\b")

_r("B3", NOT_RELEVANT, "on-site at client location", r"\b(?:on-?site|onsite|work(?:ing)?)\s+(?:at|on)\s+(?:the\s+|a\s+)?(?:client|customer)(?:'s|s')?\s+(?:location|site|office|premises|facility)\b")
_r("B3", NOT_RELEVANT, "on-site at client location", r"\bat\s+(?:the\s+)?client(?:'s|s')?\s+(?:location|site|office|premises)\b")

_r("B4", NOT_RELEVANT, "specific region only", rf"\b(?:must|need\s+to|needs\s+to|required\s+to|have\s+to)\s+(?:currently\s+)?(?:reside|live|be\s+(?:located|based|resident|residing|living))\s+(?:in|within|near)\s+(?:the\s+)?(?:state\s+of\s+|province\s+of\s+|commonwealth\s+of\s+)?(?:{_US_STATES})\b")
_r("B4", NOT_RELEVANT, "specific region only", rf"\b(?:{_US_STATES})\s+(?:residents?|based\s+(?:candidates|applicants)|candidates|applicants)\s+only\b")
_r("B4", NOT_RELEVANT, "within commuting distance", r"\bwithin\s+(?:a\s+)?\d+\s*[- ]?(?:miles?|mi|km|kilometers?)\b[^.\n;]{0,25}\b(?:of|from)\b")
_r("B4", NOT_RELEVANT, "local candidates only", r"\b(?:local\s+(?:candidates?|applicants?|only|resources?|talent)|must\s+be\s+local|(?:candidates?|applicants?)\s+(?:must\s+be\s+)?local\s+to)\b")
_r("B4", NOT_RELEVANT, "commutable distance", r"\bcommut(?:e|able|ing)\s+distance\b")
_r("B4", NOT_RELEVANT, "specific region only", r"\b(?:east|west)\s*coast\s+(?:only|candidates|based)\b|\b(?:northeast|midwest|southeast|southwest|pacific\s+northwest)\s+(?:only|based|candidates|residents)\b")

# required, recurring visits (monthly or more) = NOT relevant; rare/occasional/optional = MAYBE (H4)
_r("B5", NOT_RELEVANT, "recurring on-site visits", r"\b(?:weekly|bi-?weekly|monthly|every\s+(?:week|month|two\s+weeks)|\d+\s+(?:days?|times?)\s+(?:per|a|each)\s+(?:week|month))\b[^.\n;]{0,40}\b(?:on-?site|onsite|in[- ]person|office|visits?|travel)\b")
_r("B5", NOT_RELEVANT, "recurring on-site visits", r"\b(?:on-?site|onsite|in[- ]person|visits?\s+to\s+the\s+office)\b[^.\n;]{0,30}\b(?:weekly|bi-?weekly|monthly|every\s+(?:week|month|two\s+weeks))\b")
_r("H4", MAYBE, "occasional on-site visit / travel (check if acceptable)", r"\b(?:occasional(?:ly)?|periodic(?:ally)?|quarterly|annual(?:ly)?|infrequent(?:ly)?|rare(?:ly)?|from\s+time\s+to\s+time|as\s+needed|optional)\b[^.\n;]{0,40}\b(?:on-?site|onsite|in[- ]person|travel|visits?|trips?|office)\b", True, True)
_r("H4", MAYBE, "occasional on-site visit / travel (check if acceptable)", r"\b(?:travel|visit|report|come|on-?site|in[- ]person)\b[^.\n;]{0,80}\bonce\s+(?:per|a|every)\s+(?:quarter|year|six\s+months)\b", True, True)
_r("H4", MAYBE, "occasional on-site visit / travel (check if acceptable)", r"\b(?:one|1|two|2|three|3|four|4)\s+(?:times?|trips?|visits?)\s+(?:per|a)\s+(?:year|quarter)\b", True, True)
_r("H4", MAYBE, "mixed work arrangement", r"\b(?:work\s+arrangements?|schedule)\b[^.\n;]{0,60}\b(?:may\s+include|can\s+include|vary)\b[^.\n;]{0,60}\b(?:hybrid|on-?site)\b", True, True)

# ---------------------------------------------------------------- C: employment type
# (C3 "annual salary" was removed on request: a stated salary says nothing about whether we can serve the lead.)
_FULLTIME_OK_WORDS = re.compile(r"\b(?:contract|contractor|c2c|corp[- ]to[- ]corp|1099|temporary|temp|hourly|freelanc\w+|per\s+hour|months?|weeks?|c2h|to[- ](?:hire|perm))\b", _I)
_r("C1", NOT_RELEVANT, "full-time / permanent", r"\bjob\s*type\s*[:\-]?\s*(?:full[- ]?time|permanent)\b")
_r("C1", NOT_RELEVANT, "full-time / permanent", r"\b(?:this|the)\s+is\s+(?:a\s+)?(?:full[- ]?time|permanent)\b")
_r("C1", NOT_RELEVANT, "full-time / permanent", r"\b(?:full[- ]?time|permanent)\s+(?:position|role|employee|employment|hire|opportunity|job|basis|placement|salaried)\b")
_r("C1", NOT_RELEVANT, "FTE / direct hire", r"\bFTE\b", True, False, 0)
_r("C1", NOT_RELEVANT, "FTE / direct hire", r"\bdirect[- ]hire\b|\bdirect\s+placement\b")
_r("C1", NOT_RELEVANT, "W2 only", r"\bW-?2\s*(?:only|candidates?\s+only|employees?|position|role|basis)\b|\bonly\s+W-?2\b")
_r("C1", NOT_RELEVANT, "regular employee", r"\b(?:regular|salaried)\s+(?:full[- ]?time\s+)?employee\b")

_r("C2", NOT_RELEVANT, "employee / join our team", r"\bjoin\s+(?:our|the|a)\s+(?:growing\s+|talented\s+|dynamic\s+|amazing\s+|world-class\s+)?(?:[\w&-]+\s+){0,2}team\b")
_r("C2", NOT_RELEVANT, "offer of employment", r"\boffers?\s+of\s+employment\b|\b(?:conditional\s+)?employment\s+offer\b")
_r("C2", NOT_RELEVANT, "employee", r"\bas\s+an?\s+employee\b|\bour\s+employees\b|\bemployee\s+(?:referral|stock|discount|assistance|resource)\b")


_r("C4", NOT_RELEVANT, "employee benefits", r"\b(?:medical|dental|vision|health)\s*(?:,|and|&|/|or)?\s*(?:insurance|benefits|coverage|plans?)\b", True, True)
_r("C4", NOT_RELEVANT, "employee benefits", r"\b401\s?\(?k\)?\b|\bPTO\b|\bRRSP\b|\bESOP\b|\bRSUs?\b", True, True, 0)
_r("C4", NOT_RELEVANT, "employee benefits", r"\bpaid\s+(?:time\s+off|vacation|holidays?|leave|sick|parental)\b|\bstock\s+options?\b|\bequity\s+(?:compensation|grants?|package)\b|\bperformance\s+bonus(?:es)?\b|\bsigning\s+bonus\b|\b(?:annual|year-end)\s+bonus\b", True, True)
_r("C4", NOT_RELEVANT, "employee benefits", r"\b(?:comprehensive\s+)?benefits\s+(?:package|include|including)\b|\bemployee\s+benefits\b", True, True)

_r("C5", NOT_RELEVANT, "internal in-house hire", r"\breports?\s+(?:directly\s+)?to\s+(?:the\s+)?(?:Director|VP|Vice\s+President|CTO|CIO|CEO|CISO|Head|(?:Senior\s+)?Manager|Chief|Supervisor|Principal)\b")
_r("C5", NOT_RELEVANT, "internal in-house hire", r"\bexisting\s+vacanc\w+\b|\bbackfill\b|\breplacement\s+for\b")
_r("C5", NOT_RELEVANT, "internal in-house hire", r"\b(?:for|within|on)\s+(?:our|the)\s+(?:internal|in-?house)\s+(?:[\w&]+\s+){0,2}team\b|\bin-?house\s+(?:team|position|role|hire|developer|engineer)\b")

# ---------------------------------------------------------------- D (D1-D3 come from the eligibility filter)
_r("D4", NOT_RELEVANT, "E-Verify / I-9 / drug screen / fingerprint", r"\be-?verify\b|\bI-?9\b|\bdrug\s+(?:screen\w*|test\w*)\b|\bfingerprint\w*\b", True, True)
_r("D5", NOT_RELEVANT, "local background check", r"\bbackground\s+(?:check|investigation|screening)\b[^.\n;]{0,60}\b(?:local|resident|in[- ]person|fingerprint)\w*")
_r("D6", NOT_RELEVANT, "public-sector local residents", r"\b(?:must|required\s+to)\s+be\s+(?:a\s+)?(?:[\w-]+\s+){0,2}(?:state|county|city|commonwealth)\s+resident\b")
_r("D6", NOT_RELEVANT, "public-sector local residents", r"\b(?:state|county|city|municipal|government|public[- ]sector|commonwealth)\b[^.\n;]{0,70}\b(?:residents?|residency)\s+(?:only|required|preferred\s+or\s+required)\b")

# ---------------------------------------------------------------- E: vendor policy
_r("E1", NOT_RELEVANT, "no C2C / third parties / vendors", r"\bno\s+(?:C2C|C-?to-?C|corp[- ]to[- ]corp|third[- ]part(?:y|ies)|agenc(?:y|ies)|vendors?|brokers?|subcontract\w*|1099)\b(?!\s+(?:restrictions?|issues?|limit\w*|requirements?))", True, True)
_r("E1", NOT_RELEVANT, "no C2C / third parties / vendors", r"\b(?:C2C|corp[- ]to[- ]corp|third[- ]part(?:y|ies)|agenc(?:y|ies)|vendors?|1099s?)\b[^.\n;]{0,20}\b(?:not\s+(?:accepted|allowed|considered|permitted|eligible|acceptable)|no\s+longer)\b", True, True)
_r("E1", NOT_RELEVANT, "no C2C / third parties / vendors", r"\b(?:not|cannot|can't|unable\s+to|won't|will\s+not)\s+(?:accept|consider|work\s+with|engage|use)\s+(?:any\s+)?(?:C2C|corp[- ]to[- ]corp|third[- ]part(?:y|ies)|vendors?|agenc(?:y|ies)|subcontractors?)\b", True, True)
_r("E2", NOT_RELEVANT, "no agency submissions", r"\b(?:do(?:es)?\s+not|don't|doesn't|will\s+not|won't|cannot|can't)\s+accept\s+(?:any\s+)?(?:CVs?|resumes?|submissions?|candidates?|applications?)\s+(?:from|via|through)\s+(?:any\s+)?(?:staffing|recruit\w+|third[- ]part\w+|agenc\w+|vendors?)", True, True)
_r("E2", NOT_RELEVANT, "no agency submissions", r"\bno\s+(?:unsolicited\s+)?(?:agency\s+)?(?:resumes?|CVs?|submissions?)\s*(?:from\s+(?:agencies|vendors|recruiters))?\b[^.\n;]{0,20}\b(?:agenc\w+|recruit\w+|vendors?)", True, True)
_r("E3", NOT_RELEVANT, "vendor independence (no partner/reseller/IT services)", r"\b(?:must|should)\s+not\s+be\s+(?:a\s+|an\s+)?(?:Microsoft\s+)?(?:partner|reseller|IT\s+services?\s+provider|consult(?:ing|ancy)\s+(?:firm|company)|staffing\s+(?:firm|company))\b", True, True)
_r("E3", NOT_RELEVANT, "vendor independence (no partner/reseller/IT services)", r"\b(?:cannot|can't|may\s+not|not\s+eligible)\b[^.\n;]{0,20}\b(?:Microsoft\s+partners?|resellers?|IT\s+services?\s+providers?|system\s+integrators?)\b", True, True)
_r("E3", NOT_RELEVANT, "vendor independence (no partner/reseller/IT services)", r"\bvendor[- ]independent\b|\bindependent\s+of\s+(?:any\s+)?(?:vendor|Microsoft|reseller)\b[^.\n;]{0,30}\b(?:required|must)\b")
_r("E4", NOT_RELEVANT, "individual candidates only", r"\b(?:individuals?|individual\s+(?:candidates?|contractors?|consultants?|applicants?))\s+only\b|\bmust\s+be\s+an?\s+individual\b|\bno\s+(?:companies|firms|corporations|entities)\b|\bindividual\s+(?:candidates?|contractors?)\s+(?:only|are\s+required)\b|\bW-?2\s+(?:candidates?\s+)?only\b", True, True)
_r("E5", NOT_RELEVANT, "named agency / program experience required",
   rf"(?i:\b(?:\d+\+?\s*(?:years?|yrs?)|minimum|required|must\s+have|prior)\b[^.\n;]{{0,60}}\b(?:supporting|working\s+(?:for|with|within|on)|experience\s+(?:with|in|at|within|supporting)))\s+(?:the\s+)?(?:{_AGENCIES})\b", True, False, 0)

# ---------------------------------------------------------------- F: language
_r("F1", NOT_RELEVANT, "non-English language required",
   rf"\b(?:fluen\w+|proficien\w+|native|bilingual|speak\w*|command\s+of|written\s+and\s+spoken)\s+(?:in\s+|of\s+)?(?:\w+\s+){{0,2}}(?:{_LANGS})\b")
_r("F1", NOT_RELEVANT, "non-English language required",
   rf"\b(?:{_LANGS})\s+(?:language\s+)?(?:fluency|proficiency|is\s+(?:required|mandatory|essential|a\s+must)|required|mandatory)\b")
_r("F1", NOT_RELEVANT, "non-English language required", rf"\b(?:{_LANGS})[- ]speaking\b|\b(?:in|and)\s+(?:{_LANGS})\s+(?:and|&|/)\s+English\b")

# ---------------------------------------------------------------- G: role type
_r("G1", NOT_RELEVANT, "role with direct reports", r"\bdirect\s+reports?\b|\bmanage[sd]?\s+(?:a\s+)?team\s+of\s+\d+|\bpeople\s+manag\w+|\bsupervis(?:e|es|ing)\s+(?:a\s+)?(?:team|staff|engineers|developers|analysts)\b|\bline\s+manag\w+|\bresponsible\s+for\s+(?:hiring|managing)\s+(?:and\s+(?:managing|developing)\s+)?(?:a\s+)?team\b")
_r("G2", NOT_RELEVANT, "role that represents the company publicly", r"\b(?:developer\s+(?:advocate|relations|evangelist)|devrel|evangelist|pre-?sales|sales\s+engineer|solutions?\s+engineer\s*\(?pre-?sales\)?|brand\s+ambassador|technical\s+evangelist)\b")
_r("G2", NOT_RELEVANT, "role that represents the company publicly", r"\b(?:represent(?:s|ing)?\s+(?:the\s+)?company\s+(?:at|in|to)\s+(?:conferences?|events?|the\s+public)|speak(?:ing)?\s+at\s+conferences?|public\s+speaking|customer[- ]facing\s+sales)\b")
_r("G4", NOT_RELEVANT, "regulated bid (dated project-level proof)", r"\b(?:resumes?|CVs?)\b[^.\n;]{0,40}\b(?:must|should|will)\s+(?:clearly\s+)?(?:show|demonstrate|include|list|specify)\b[^.\n;]{0,80}\b(?:dates?|month|year|duration)\b")
_r("G4", NOT_RELEVANT, "regulated bid (dated project-level proof)", r"\beach\s+(?:mandatory\s+)?(?:requirement|qualification)\b[^.\n;]{0,80}\b(?:dates?|months?|proof|demonstrat\w+|project)\b")
_r("G4", NOT_RELEVANT, "regulated bid (dated project-level proof)", r"\b(?:RFP|RFQ|solicitation)\s*(?:number|no\.?|#|response)\b|\bmandatory\s+requirements?\b[^.\n;]{0,60}\bproof\b")

# ---------------------------------------------------------------- H: maybe
_r("H2", MAYBE, "contract-to-hire", r"\bcontract[- ]to[- ](?:hire|perm\w*|permanent)\b|\bC2H\b|\btemp[- ]to[- ](?:hire|perm\w*)\b|\bcontract\s+with\s+(?:the\s+)?(?:possibility|potential|option)\s+(?:of|for)\s+(?:conversion|permanent|hire)", True, True)
_r("H3", MAYBE, "strict time-zone rule", r"\b(?:EST|EDT|CST|CDT|MST|MDT|PST|PDT|Eastern|Central|Mountain|Pacific)\s+(?:time\s*zone\s+)?(?:hours|only|business\s+hours|working\s+hours)\b", True, True)
_r("H3", MAYBE, "strict time-zone rule", r"\b(?:work|working|available|availability|overlap)\w*\b[^.\n;]{0,45}\b(?:EST|EDT|CST|CDT|MST|MDT|PST|PDT)\b", True, True, 0)
_r("H3", MAYBE, "strict time-zone rule", r"\b(?:night|overnight|graveyard)\s+shift\b|\b\d+\s+hours?\s+of\s+overlap\b", True, True)
_r("H6", MAYBE, "talent pool / no live requirement", r"\b(?:talent\s+(?:pool|community|network)|join\s+our\s+(?:freelanc\w+\s+)?network|future\s+(?:opportunit\w+|openings?)|anticipated\s+(?:and\s+upcoming\s+)?opportunit\w+|upcoming\s+opportunit\w+|no\s+live\s+(?:requirement|opening)|always\s+looking\s+for)\b", True, True)
_r("H7", MAYBE, "part-time", r"\bpart[- ]time\b", True, True)

_ENGAGEMENT_EVIDENCE = re.compile(
    r"\b(?:contract(?:or)?|C2C|corp[- ]to[- ]corp|1099|freelanc\w+|project[- ]based|hourly|per\s+hour|/\s*h(?:ou)?r\b|"
    r"\d+\s*[- ]?(?:month|week)s?\b|fixed[- ](?:term|duration)|temporary|short[- ]term|statement\s+of\s+work)\b", _I)
_REMOTE_EVIDENCE = re.compile(r"\b(?:remote|work\s+from\s+home|telecommut\w+|WFH|work\s+from\s+anywhere|virtual)\b", _I)
_REMOTE_EXPLICIT = re.compile(r"\b(?:100\s*%|fully|completely|entirely)\s+remote\b|\bremote\s+(?:position|role|opportunity|job)\b|\bwork\s+from\s+home\b", _I)
_RATE_RE = re.compile(r"(?:\$|USD|US\$)\s?(\d{1,3}(?:\.\d+)?)\s*(?:-|–|to)?\s*(?:\$|USD)?\s?(\d{1,3}(?:\.\d+)?)?\s*(?:/|per|an?)\s*(?:hr|hour)\b", _I)
_ANY_RATE_RE = re.compile(r"(?:\$|USD|£|€)\s?\d|\b\d+\s*(?:/|per)\s*(?:hr|hour)\b|\brate\b[^.\n]{0,20}\d|\bpay\s*[:\-]", _I)
_TRAVEL_PCT = [re.compile(r"\btravel\w*\b[^.\n;]{0,30}?(\d{2,3})\s*%", _I), re.compile(r"(\d{2,3})\s*%\s*(?:of\s+(?:the\s+)?time\s+)?travel\b", _I)]
_TRAVEL_MIN_PCT = 25
_THIN_POST_CHARS = 250
_GLOBAL_OK = re.compile(
    r"\bworldwide\b|\bglobal(?:ly)?\s+(?:remote|team|candidates|talent|hiring|position|role)\b|\banywhere\s+in\s+the\s+world\b|"
    r"\bwork\s+from\s+anywhere\b|\bany\s+country\b|\binternational\s+(?:candidates|applicants)\b|"
    r"\bopen\s+to\s+(?:all|any)\s+(?:countries|locations)\b|\boffshore\b|\bnearshore\b", _I)
_PLACE_RE = re.compile(r"\b[A-Z][A-Za-z.'\-]+(?:\s[A-Z][A-Za-z.'\-]+)*,\s*[A-Z]{2}\b(?:\s+\d{5})?")
_LOCATION_LINE = re.compile(r"^\s*(?:job\s+)?location\s*[:\-]\s*(.+)$", _I)


def _tied_place(location: str) -> str:
    """'Remote in Minneapolis, MN (Fully Remote)' -> 'Minneapolis, MN'; 'Remote (Fully Remote)' -> ''."""
    loc = re.sub(r"\((?:fully\s+)?remote\)|\(hybrid\)|\(on-?site\)", "", location or "", flags=_I).strip()
    m = _PLACE_RE.search(loc)
    if not m:
        return ""
    place = m.group(0).strip()
    return "" if re.match(r"(?:remote|fully|hybrid)\b", place, _I) else place
_ENGLISH_STOP = {"the", "and", "to", "of", "a", "in", "for", "with", "is", "on", "as", "you", "will", "are", "be", "we", "our", "or", "that"}
_FOREIGN_STOP = {
    # German / French / Spanish / Portuguese / Italian / Dutch function words that are not English words
    "und", "der", "die", "das", "mit", "fuer", "für", "ein", "eine", "sie", "wir", "nicht", "bei", "oder",
    "le", "la", "les", "des", "une", "pour", "avec", "dans", "est", "nous", "vous", "sur", "pas", "qui",
    "el", "los", "las", "para", "con", "una", "por", "del", "que", "como", "nuestro", "somos", "tu",
    "uma", "não", "são", "você", "também", "com", "do", "da", "dos",
    "il", "che", "per", "della", "nel", "sono", "alla", "gli", "di", "non",
    "het", "een", "van", "voor", "zijn", "wij", "niet",
}
_AGGREGATOR_HINT = re.compile(r"\b(?:my|our)\s+client\b", _I)
_STRONG_ENGAGEMENT = re.compile(r"\b(?:contract(?:or)?|C2C|corp[- ]to[- ]corp|1099|freelanc\w+|project[- ]based|fixed[- ](?:term|duration)|temporary|statement\s+of\s+work|\d+\s*[- ]?(?:month|week)s?)\b", _I)

# --- title rules (G1/G2/G3) -----------------------------------------------------------------------------
_TITLE_G1_DEFAULT = ["vice president", "vp", "svp", "evp", "avp", "director", "head of", "chief", "president", "manager",
                     "managing director", "general manager", "supervisor", "scrum master", "product owner"]
_TITLE_G2 = re.compile(r"\b(?:developer\s+advocate|devrel|evangelist|pre-?sales|sales\s+engineer|sales|account\s+executive|business\s+development)\b", _I)
_TITLE_G3 = re.compile(r"\b(?:ui\s*/?\s*ux|ux\s*/?\s*ui|ux|product\s+designer|designer|graphic|recruit\w*|talent\s+acquisition|marketing|seo|content\s+(?:writer|creator|strategist)|copywriter|social\s+media)\b", _I)
_TITLE_BA = re.compile(r"\bbusiness\s+(?:systems?\s+)?analyst\b|\bBA\b", _I | 0)
_BA_INTERNAL_DOMAIN = re.compile(r"\b(?:HR|human\s+resources|payroll|finance|financial|accounting|treasury|procurement|supply\s+chain|sales\s+operations)\b", _I)


def _title_g1_regex() -> re.Pattern:
    terms = list(_TITLE_G1_DEFAULT)
    path = Path(__file__).resolve().parent.parent.parent / "config" / "lead_rules.json"
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("title_reject_always"), list) and data["title_reject_always"]:
                terms = [str(t) for t in data["title_reject_always"]]
    except Exception:
        pass
    body = "|".join(re.escape(t.strip()) for t in terms if t.strip())
    return re.compile(rf"(?<![\w])(?:{body})(?![\w])", _I)


_TITLE_G1 = _title_g1_regex()

def _gig_regexes() -> list[re.Pattern]:
    pats = ["per (?:completed )?task", "data annotation"]
    path = Path(__file__).resolve().parent.parent.parent / "config" / "lead_rules.json"
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("gig_signals"), list) and data["gig_signals"]:
                pats = [str(p) for p in data["gig_signals"]]
    except Exception:
        pass
    return [re.compile(p, _I) for p in pats]


_GIG_RES = _gig_regexes()

_ELIG_TO_RULE = {
    "citizenship": "D1", "permanent residency": "D1", "export control": "D1",
    "security clearance": "D2", "work authorization": "D3", "visa": "D3", "residency": "B4",
}


@dataclass
class Hit:
    rule: str
    decision: str
    label: str
    snippet: str

    @property
    def short(self) -> str:
        quote = re.sub(r"\s+", " ", self.snippet).strip("… ")
        if len(quote) > 70:
            quote = quote[:67].rstrip() + "..."
        return f'{self.label}: "{quote}"' if quote else self.label


@dataclass
class RuleOutcome:
    decision: str = RELEVANT
    rule: str = ""
    reason: str = ""
    hits: list[Hit] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)  # MAYBE rule ids

    @property
    def label(self) -> str:
        return f"[{self.rule}] {self.reason}" if self.rule else self.reason


def _snip(seg: str, m: re.Match) -> str:
    return elig._snippet(seg, m)


def _join_label_lines(text: str) -> str:
    """'Job Type:\nFull-Time' -> 'Job Type: Full-Time' so label and value are one sentence for the rules."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i].rstrip()
        if cur.endswith(":") and 2 <= len(cur) <= 40 and i + 1 < len(lines):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and 0 < len(lines[j].strip()) <= 90 and not lines[j].rstrip().endswith(":"):
                out.append(f"{cur} {lines[j].strip()}")
                i = j + 1
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _looks_non_english(text: str) -> bool:
    words = re.findall(r"[A-Za-zÀ-ÿ']+", text.lower())
    if len(words) < 40:
        return False  # too short to judge; terse English ("Remote contract, 6 months") must never be flagged
    n = len(words)
    en = sum(1 for w in words if w in _ENGLISH_STOP) / n
    foreign = sum(1 for w in words if w in _FOREIGN_STOP) / n
    return en < 0.04 and foreign > 0.08


def evaluate(title: str, text: str, salary_range: str = "", location_remote: str = "", job_type_hint: str = "") -> RuleOutcome:
    """Run the whole rulebook over a posting. Never raises (a bad rule must not stop a scrape)."""
    try:
        return _evaluate(title or "", text or "", salary_range or "", location_remote or "")
    except Exception as exc:
        logger.error("Rulebook evaluation failed for '{}': {}", title, exc)
        return RuleOutcome()


def _evaluate(title: str, text: str, salary_range: str, location_remote: str) -> RuleOutcome:
    hits: list[Hit] = []
    body = elig._TAG_RE.sub("", elig._BLOCK_TAG_RE.sub("\n", f"{title}\n{text}"))
    body = re.sub(r"\bU\.\s?S\.\s?A\b\.?", "USA", body)
    body = re.sub(r"\bU\.\s?S\b\.?", "US", body)
    body = re.sub(r"\bU\.\s?K\b\.?", "UK", body)
    # structured card fields are evidence too (e.g. "USD105,000 - USD140,000 per year")
    sal = salary_range.strip()
    extra = f"\nSalary: {sal}" if sal and sal.lower() not in ("not listed", "n/a", "") else ""
    full = _join_label_lines(body) + extra

    has_contract_evidence = bool(_ENGAGEMENT_EVIDENCE.search(full))
    remote_explicit = bool(_REMOTE_EXPLICIT.search(title + "\n" + text))

    # ---- title rules -------------------------------------------------------------------------------------
    if _TITLE_G1.search(title):
        hits.append(Hit("G1", NOT_RELEVANT, "Management / leadership role", title.strip()))
    if _TITLE_G2.search(title):
        hits.append(Hit("G2", NOT_RELEVANT, "Sales / public-facing role", title.strip()))
    if _TITLE_G3.search(title) and not re.search(r"\b(?:developer|engineer|architect|programmer|devops)\b", title, _I):
        hits.append(Hit("G3", NOT_RELEVANT, "Non-engineering role", title.strip()))
    if _TITLE_BA.search(title):
        if _BA_INTERNAL_DOMAIN.search(title + "\n" + text[:300]):
            hits.append(Hit("G3", NOT_RELEVANT, "Business analyst for an internal HR/finance function", title.strip()))
        else:
            hits.append(Hit("G3", MAYBE, "Business analyst role - check it is engineering work", title.strip()))

    # ---- B4: remote, but tied to a specific city / state (we work from India) --------------------------------------
    if not _GLOBAL_OK.search(full):
        place = _tied_place(location_remote)
        if not place:
            for line in body.split("\n"):
                lm = _LOCATION_LINE.match(line)
                if lm and _tied_place(lm.group(1)):
                    place = _tied_place(lm.group(1))
                    break
        if place:
            hits.append(Hit("B4", NOT_RELEVANT, "Remote role tied to a specific place, not open globally", f"Location: {place}"))

    # ---- gig / crowd work (AI training, annotation, per-task pay) is not an engineering engagement (G3) -----------
    for grx in _GIG_RES:
        gm = grx.search(full)
        if gm:
            hits.append(Hit("G3", NOT_RELEVANT, "Per-task / AI-training gig work, not an engineering engagement",
                            full[max(0, gm.start() - 40):gm.end() + 40].strip()))
            break

    # ---- eligibility (D1-D3, B4): existing, tested filter -------------------------------------------------
    ev = elig.check_text(text, title)
    if ev.restricted:
        for cat, snippet in ev.hits:
            rule = _ELIG_TO_RULE.get(cat)
            if rule:
                label = elig.EligibilityVerdict(restricted=True, category=cat, snippet=snippet).short_reason
                hits.append(Hit(rule, NOT_RELEVANT, label.split(': "')[0], snippet))

    # ---- pattern rules over segments ------------------------------------------------------------------------
    for seg, in_opt, in_req in elig._segments(full):
        seg_optional = bool(elig._OPTIONAL.search(seg))
        seg_mandatory = bool(elig._MANDATORY.search(seg)) or in_req
        for rule, decision, label, rx, inherent, ignore_opt in _PATTERNS:
            m = rx.search(seg)
            if not m:
                continue
            if not ignore_opt and (in_opt or seg_optional):
                continue
            if ignore_opt and in_opt and rule not in ("D4", "E1", "E2", "E3", "E4"):
                continue
            if not inherent and not seg_mandatory:
                continue
            # employment-type rules are about permanence: contract wording in the same sentence overrides
            if rule == "C1" and label in ("full-time / permanent",) and _FULLTIME_OK_WORDS.search(seg):
                continue
            if rule == "C2" and label == "employee / join our team" and has_contract_evidence:
                continue
            if rule in ("C1", "C2") and re.search(r"contract[- ]to[- ](?:hire|perm)", seg, _I):
                continue
            # a hybrid/on-site mention that contradicts an explicit "100% remote" in the same post is I2 (MAYBE)
            if rule == "B1" and remote_explicit and not _REMOTE_EXPLICIT.search(seg):
                hits.append(Hit("I2", MAYBE, "Post conflicts with itself (remote vs on-site)", _snip(seg, m)))
                continue
            hits.append(Hit(rule, decision, label, _snip(seg, m)))

    # ---- B3: travel percentage ------------------------------------------------------------------------------
    for rx in _TRAVEL_PCT:
        for m in rx.finditer(full):
            ctx = full[max(0, m.start() - 60):m.end() + 40]
            if int(m.group(1)) >= _TRAVEL_MIN_PCT and not elig._OPTIONAL.search(ctx):
                hits.append(Hit("B3", NOT_RELEVANT, f"Travel of {m.group(1)}% or more", ctx.strip()))
                break

    # ---- F2: post written in another language ----------------------------------------------------------------
    if _looks_non_english(text):
        hits.append(Hit("F2", MAYBE, "Post is not written in English", text[:60]))

    # ---- H1: remote / contract not clearly stated ------------------------------------------------------------
    remote_known = bool(_REMOTE_EVIDENCE.search(full)) or "remote" in (location_remote or "").lower()
    if not remote_known:
        hits.append(Hit("H1", MAYBE, "Remote work is not clearly stated", ""))
    if not has_contract_evidence and not any(h.rule == "H2" for h in hits):
        hits.append(Hit("H1", MAYBE, "Contract / project engagement is not clearly stated", ""))

    # ---- H5: recruiter "my client" with no engagement details ----------------------------------------------------
    if _AGGREGATOR_HINT.search(full) and len(text) < 700 and not _STRONG_ENGAGEMENT.search(full):
        hits.append(Hit("H5", MAYBE, 'Recruiter post ("my client") without engagement details', ""))

    # ---- H8: rate missing / far outside the normal range (only matters for would-be relevant leads) --------------
    if not _ANY_RATE_RE.search(full):
        hits.append(Hit("H8", MAYBE, "Rate is not stated", ""))
    else:
        for m in _RATE_RE.finditer(full):
            lo = float(m.group(1))
            hi = float(m.group(2) or m.group(1))
            from app.config.settings import get_settings
            s = get_settings()
            lo_cap, hi_cap = getattr(s, "rulebook_rate_min", 20), getattr(s, "rulebook_rate_max", 150)
            if hi < lo_cap or lo > hi_cap:
                hits.append(Hit("H8", MAYBE, f"Hourly rate ${lo:g}-{hi:g} is outside our normal range", m.group(0)))
            break

    return _decide(hits)


def _decide(hits: list[Hit]) -> RuleOutcome:
    nots = [h for h in hits if h.decision == NOT_RELEVANT]
    maybes = [h for h in hits if h.decision == MAYBE]
    if nots:
        nots.sort(key=lambda h: _PRIORITY.index(h.rule) if h.rule in _PRIORITY else 99)
        first = nots[0]
        seen, also = {first.rule}, []
        for h in nots[1:]:
            if h.rule not in seen:
                seen.add(h.rule)
                also.append(h.rule)
        reason = first.short + (f" (also {', '.join(also[:3])})" if also else "")
        return RuleOutcome(NOT_RELEVANT, first.rule, reason, hits, [])
    if maybes:
        uniq: dict[str, Hit] = {}
        for h in maybes:
            uniq.setdefault(h.rule, h)
        first = next(iter(uniq.values()))
        # H8 / H1 are weak signals: only the strong ones lead the reason
        ordered = sorted(uniq.values(), key=lambda h: {"I2": 0, "H2": 1, "H3": 1, "H4": 1, "H5": 1, "H6": 1, "H7": 1, "G3": 1, "F2": 1, "H1": 2, "H8": 3}.get(h.rule, 2))
        first = ordered[0]
        return RuleOutcome(MAYBE, first.rule, first.short, hits, list(uniq))
    return RuleOutcome(RELEVANT, "A", "Passes the must-pass rules (remote, contract/project, open to vendors)", hits, [])


# ---------------------------------------------------------------- applying to a JobPosting
def apply_rulebook(job) -> RuleOutcome:
    """Evaluate `job`. NOT RELEVANT -> mark it Rejected (with the rule id) and return; MAYBE/RELEVANT are left for the
    LLM stage and settled in finalize_rulebook()."""
    outcome = evaluate(job.job_title, job.job_description, getattr(job, "salary_range", ""),
                       getattr(job, "location_remote_type", "") or "")
    job.rule_flags = list(outcome.flags)
    if outcome.decision == NOT_RELEVANT:
        group = RULE_GROUP.get(outcome.rule[:1], "Rule")
        job.lead_class = "Rejected"
        job.lead_score = 0
        job.lead_category = group
        job.lead_rule = outcome.rule
        job.lead_reason = f"[{outcome.rule}] {outcome.reason}"
        job.reject_reason = f"[{outcome.rule}] {outcome.reason}"
        job.engagement_type = "eligibility_restricted" if outcome.rule.startswith("D") else "rule_rejected"
    return outcome


def apply_rules_stage(job, rulebook_on: bool, eligibility_on: bool) -> Optional[RuleOutcome]:
    """The rules stage every pipeline (Indeed, Dice, Manual) runs BEFORE any LLM call.

    rulebook on  -> full rulebook A-I (it already includes the eligibility rules D1-D3 / B4).
    rulebook off -> just the eligibility filter (previous behaviour).
    A NOT RELEVANT result marks the job Rejected, so the caller skips the LLM and KB steps entirely."""
    if rulebook_on:
        return apply_rulebook(job)
    if eligibility_on:
        elig.apply_eligibility(job)
    return None


def finalize_rulebook(job, outcome: RuleOutcome) -> None:
    """After the LLM stage: a MAYBE outcome caps the lead at Needs Review; a clean pass without an LLM verdict becomes Relevant."""
    if outcome is None:
        return
    if job.lead_class == "Rejected":
        # A one-sentence post gives the LLM nothing to judge: its "internal hire" guess is not a real rejection.
        # (Hard rejections - rulebook rules, eligibility, titles - are left alone.)
        thin = len((job.job_description or "").strip()) < _THIN_POST_CHARS
        llm_guess = (job.engagement_type or "") in ("internal_hire", "unclear", "") and not job.lead_rule
        if outcome.decision == MAYBE and thin and llm_guess:
            job.lead_class = "Needs Review"
            job.lead_score = 40
            job.reject_reason = ""
            job.lead_rule = outcome.rule
            job.lead_reason = f"[{outcome.rule}] {outcome.reason}. Too little text to judge - manual review."
        return
    if outcome.decision == MAYBE:
        job.lead_rule = outcome.rule
        if job.lead_class in ("", "High Priority", "Relevant"):
            job.lead_class = "Needs Review"
            job.lead_score = min(job.lead_score or 50, 54) if job.lead_score else 50
            job.lead_reason = f"[{outcome.rule}] {outcome.reason}. {job.lead_reason or ''}".strip()
    elif outcome.decision == RELEVANT and not job.lead_class:
        job.lead_class = "Relevant"
        job.lead_rule = "A"
        job.lead_reason = f"[A] {outcome.reason}"
