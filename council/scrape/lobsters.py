import httpx
from typing import Any, Dict, List


def scrape_lobsters(max_results: int = 30) -> List[Dict[str, Any]]:
    """
    Scrapes Lobste.rs for hottest stories using their JSON API.
    Returns a list of dictionaries containing title, url, tags, and description.
    """
    url = "https://lobste.rs/hottest.json"

    results = []
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        for item in data[:max_results]:
            tags = item.get("tags", [])
            tag_str = ", ".join(tags) if isinstance(tags, list) else str(tags)

            results.append({
                "source": "Lobste.rs",
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "blurb": f"Tags: {tag_str}\n{item.get('description', '')[:200]}",
                "scraped_at": item.get("created_at")
            })

    except Exception as e:
        print(f"Error scraping Lobste.rs: {e}")

    return results


if __name__ == "__main__":
    import json
    data = scrape_lobsters(max_results=5)
    print(json.dumps(data, indent=2))
    print(f"Total items scraped: {len(data)}")