import httpx
from typing import Any, Dict, List

def scrape_devto(per_page: int = 30) -> List[Dict[str, Any]]:
    """
    Scrapes DEV.to for recent articles using their official API.
    Returns a list of dictionaries containing title, url, tags, and description.
    """
    url = "https://dev.to/api/articles"
    params = {
        "per_page": per_page
    }

    results = []
    try:
        response = httpx.get(url, params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        for item in data:
            # Join tags if it's a list, otherwise default to string representation or empty
            tags = item.get("tag_list", [])
            tag_str = ", ".join(tags) if isinstance(tags, list) else str(tags)

            # Use description as blurb, fallback to an empty string
            description = item.get("description", "")

            results.append({
                "source": "DEV.to",
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "blurb": f"Tags: {tag_str}\n{description}",
                "scraped_at": item.get("published_at")
            })

    except Exception as e:
        print(f"Error scraping DEV.to: {e}")

    return results

if __name__ == "__main__":
    import json
    data = scrape_devto(per_page=5)
    print(json.dumps(data, indent=2))
    print(f"Total items scraped: {len(data)}")
