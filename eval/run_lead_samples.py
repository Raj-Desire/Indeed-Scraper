"""Run realistic postings through the real lead classifier and compare with the expected outcome."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.matching.lead_classifier import LeadClassifier, get_lead_classifier  # noqa: E402

# (title, company, description, expected: "accept" | "review" | "reject")
SAMPLES = [
    ("Senior .NET Developer (Contract, C2C)", "Prime Source Technologies",
     "Our client, a Fortune 500 insurer, needs two .NET Core developers on a 6-month contract (C2C/1099 welcome) "
     "to build REST APIs and migrate a legacy WCF system to Azure. Remote. Corp-to-corp preferred.", "accept"),
    ("Dynamics 365 CRM Implementation Consultant", "Apex Consulting Group",
     "We are a consulting firm delivering Dynamics 365 CE implementations for mid-market clients. Looking for "
     "implementation consultants to staff upcoming client projects: requirements, configuration, data migration, go-live.", "accept"),
    ("AI/ML Engineer - Dedicated Offshore Team", "NovaStack Labs",
     "We are looking for an external development partner / dedicated team of 4 ML engineers to build a computer "
     "vision platform for our manufacturing client. Project-based, SOW, 9 months.", "accept"),
    ("Software Engineer", "Brightline Health",
     "Join our in-house engineering team! Full-time permanent role. You will work on our patient portal in React and "
     "Node. Benefits include medical, dental, 401(k), paid time off and stock options. Reports to the VP Engineering.", "reject"),
    ("Backend Developer", "Kestrel Fintech",
     "We're a fast-growing startup hiring our 5th backend engineer. Permanent position, equity, great company culture. "
     "Python/Django, PostgreSQL. Join our internal team in Austin.", "reject"),
    ("Sales Executive - Software Solutions", "TechBridge Inc",
     "Drive new business for our software products. Quota carrying, cold outreach, CRM management, close enterprise deals.", "reject"),
    ("IT Recruiter", "Talent Hive",
     "Source and screen candidates for technical roles, manage the full recruitment lifecycle, partner with hiring managers.", "reject"),
    ("Marketing Manager", "CloudNine SaaS", "Own demand generation, SEO, email campaigns, and brand strategy.", "reject"),
    ("Office Administrator", "Delta Logistics", "Answer phones, schedule meetings, manage office supplies, support the team.", "reject"),
    ("SharePoint Developer", "Meridian IT Services",
     "Staffing opportunity: SharePoint Online / SPFx developer for our client (government agency), 12-month contract "
     "with extension, remote. W2 or C2C.", "accept"),
    ("Technical Project Manager", "Orion Systems",
     "Coordinate sprints, manage stakeholders and timelines, run status meetings, track budgets. Light technical background.", "reject"),
    ("Full Stack Developer", "Unnamed Company",
     "We need a developer for a few months to help with a website. React and Node. Details to be discussed.", "review"),
]


async def main():
    clf = get_lead_classifier()
    ok = 0
    for title, company, desc, expected in SAMPLES:
        v = await clf.classify(title, company, desc)
        got = {"High Priority": "accept", "Relevant": "accept", "Needs Review": "review", "Rejected": "reject"}[v.lead_class]
        match = got == expected or (expected == "review" and got in ("review", "accept"))
        ok += match
        print(f"{'OK  ' if match else 'MISS'} exp={expected:6} got={v.lead_class:13} score={v.lead_score:3} "
              f"eng={v.engagement:20} | {title[:44]}\n       {v.reason[:150]}")
    print(f"\n{ok}/{len(SAMPLES)} as expected")


asyncio.run(main())
