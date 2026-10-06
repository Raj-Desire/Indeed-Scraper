import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.knowledge_base.azure_search import AzureSearchKnowledgeBase
QS = sys.argv[1:]
async def main():
    kb = AzureSearchKnowledgeBase()
    for q in QS:
        res = await kb.search(q, top_k=4)
        print("\nQ:", q)
        for c in res: print("  -", round(c.score,3), c.title[:30], "|", c.chunk[:260].replace("\n"," "))
    await kb.close()
asyncio.run(main())
