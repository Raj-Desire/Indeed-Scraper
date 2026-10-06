"""Run the sample JDs through the real engine and print what it extracts/decides."""
import asyncio, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sample_jds import SAMPLES
from app.knowledge_base.azure_search import AzureSearchKnowledgeBase
from app.matching.engine import MatchEngine
from app.matching.llm_matcher import LLMMatcher
from app.utils.helpers import extract_salary_range


async def main():
    kb, llm = AzureSearchKnowledgeBase(), LLMMatcher()
    eng = MatchEngine(kb, llm)
    for name, jd in SAMPLES.items():
        t = time.time()
        r = await eng.evaluate(jd, name)
        print(f"\n=== {name} ({time.time()-t:.1f}s) salary={extract_salary_range(jd)}")
        print(" status:", r.match_status, "score:", r.match_score)
        print(" matched:", r.matched_skills)
        print(" missing:", r.missing_skills)
        print(" reason:", r.match_reason)
    await kb.close(); await llm.close()

asyncio.run(main())
