import httpx
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

def scrape_arxiv(categories: List[str] = None, max_results: int = 30) -> List[Dict[str, Any]]:
    """
    Scrapes arXiv for recent papers in the specified categories using the official API.
    Returns a list of dictionaries containing title, url, and truncated abstract.
    """
    if categories is None:
        categories = ["cs.CV", "cs.LG", "cs.SE", "cs.RO"]

    url = "https://export.arxiv.org/api/query"
    search_query = " OR ".join([f"cat:{cat}" for cat in categories])

    params = {
        "search_query": search_query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results
    }

    results = []
    try:
        response = httpx.get(url, params=params, timeout=10.0)
        response.raise_for_status()

        # Parse XML response
        root = ET.fromstring(response.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
            link = entry.find("atom:id", ns).text.strip()
            summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
            published = entry.find("atom:published", ns).text.strip()

            # Truncate blurb to ~200 characters
            blurb = summary[:200] + "..." if len(summary) > 200 else summary

            results.append({
                "source": "arXiv",
                "title": title,
                "url": link,
                "blurb": blurb,
                "scraped_at": published
            })

    except Exception as e:
        print(f"Error scraping arXiv: {e}")

    return results

if __name__ == "__main__":
    import json
    data = scrape_arxiv(max_results=5)
    print(json.dumps(data, indent=2))
    print(f"Total items scraped: {len(data)}")
