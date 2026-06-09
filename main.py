from pprint import pprint
from council.scrape.arxiv import scrape_arxiv
from council.scrape.hn import scrape_hn
from council.scrape.devto import scrape_devto

# print("arxiv: ")
pprint(scrape_arxiv()[0])
#
#
# print("devto: ")
# print(scrape_devto())
#
#
# print("hn: ")
# print(scrape_hn())
