import httpx
from typing import Any, Dict, List

def scrape_hn() -> List[Dict[str, Any]]:
    """
    Scrapes the Hacker News front page and 'Ask HN' using the official Algolia API.
    Returns a list of dictionaries containing title, url, score, and source.
    """
    url = "https://hn.algolia.com/api/v1/search"
    results = []

    # Fetch front page
    try:
        response = httpx.get(url, params={"tags": "front_page"}, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        for item in data.get("hits", []):
            results.append({
                "source": "Hacker News",
                "title": item.get("title", ""),
                "url": item.get("url") or f"https://news.ycombinator.com/item?id={item.get('objectID')}",
                "blurb": f"Points: {item.get('points', 0)} | Comments: {item.get('num_comments', 0)}",
                "scraped_at": item.get("created_at")
            })
    except Exception as e:
        print(f"Error scraping HN front page: {e}")

    # Fetch Ask HN
    try:
        response = httpx.get(url, params={"tags": "ask_hn"}, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        for item in data.get("hits", []):
            results.append({
                "source": "Ask HN",
                "title": item.get("title", ""),
                "url": f"https://news.ycombinator.com/item?id={item.get('objectID')}",
                "blurb": f"Points: {item.get('points', 0)} | Comments: {item.get('num_comments', 0)}\n{item.get('story_text', '')[:200]}...",
                "scraped_at": item.get("created_at")
            })
    except Exception as e:
        print(f"Error scraping Ask HN: {e}")

    return results

if __name__ == "__main__":
    import json
    data = scrape_hn()
    print(json.dumps(data[:3], indent=2))
    print(f"Total items scraped: {len(data)}")
