from bs4 import BeautifulSoup
import re

with open("tests/fixtures/indeed_search_results.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")
scripts = soup.find_all("script")
for i, s in enumerate(scripts):
    text = s.string or ""
    if "jobDescription" in text or "jobkey" in text or "formattedLocation" in text:
        print(f"Script {i} matches keywords, length: {len(text)}")
        matches = re.findall(r'"jobkey":"([^"]+)".*?"snippet":"([^"]+)"', text)
        print("Found jobkey-snippet matches:", len(matches))
        if matches:
            print("First match:", matches[0][0], "->", matches[0][1][:150])
