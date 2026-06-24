from pprint import pprint

from council.scrape.arxiv import scrape_arxiv

signal = scrape_arxiv(max_results=1)

pprint(signal)
