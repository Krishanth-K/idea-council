import httpx
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List


def scrape_github(max_results: int = 30) -> List[Dict[str, Any]]:
    """
    Scrapes GitHub for trending repositories using the Search API.
    Returns a list of dictionaries containing name, description, language, and stars.
    """
    url = "https://api.github.com/search/repositories"

    # Get repos created in the last 7 days, sorted by stars
    date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    params = {
        "q": f"created:>{date}",
        "sort": "stars",
        "order": "desc",
        "per_page": min(max_results, 100)
    }

    headers = {}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    results = []
    try:
        response = httpx.get(url, params=params, headers=headers, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        for item in data.get("items", []):
            lang = item.get("language", "N/A")
            results.append({
                "source": "GitHub",
                "title": item.get("name", ""),
                "url": item.get("html_url", ""),
                "blurb": f"Language: {lang} | Stars: {item.get('stargazers_count', 0)}\n{item.get('description', '')[:200]}",
                "scraped_at": item.get("created_at")
            })

    except Exception as e:
        print(f"Error scraping GitHub: {e}")

    return results


if __name__ == "__main__":
    import json
    data = scrape_github(max_results=5)
    print(json.dumps(data, indent=2))
    print(f"Total items scraped: {len(data)}")