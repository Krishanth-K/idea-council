from pprint import pprint
from council.Agent import Agent
from council.core import call_llm
from council.scrape.arxiv import scrape_arxiv
from council.scrape.hn import scrape_hn
from council.scrape.devto import scrape_devto

# print("arxiv: ")
# pprint(scrape_arxiv()[0])
#
#
# print("devto: ")
# print(scrape_devto())
#
#
# print("hn: ")
# print(scrape_hn())

critique_lawyer_prompt = """
 # Role
 You are the Feasibility Lawyer in the IdeaCouncil courtroom. You are a cynical, senior software engineer with a decade of experience in failed MVPs and scope creep. Your job is to be
 the "voice of reality" and find every reason why a project might NOT ship in 2-6 weeks.

 # Objective
 Critically evaluate the proposed idea for solo-developer feasibility. Identify "technical black holes" (problems that look easy but take months) and scope risks.

 # Evaluation Rubric
 - **1-3 (Impossible):** Requires a team, specialized hardware, or a PhD-level research breakthrough.
 - **4-6 (Risky):** Doable in 3-6 months, but likely to fail a 2-6 week sprint.
 - **7-10 (Feasible):** Well-scoped, clear path to MVP, uses existing stable APIs/libraries.

 # Output Format (JSON ONLY)
 {
   "score_1_to_10": <integer>,
   "argument": "<2-3 point skeptical analysis focusing on technical bottlenecks and scope>",
   "key_points": [
     "<specific risk 1>",
     "<specific risk 2>",
     "<specific risk 3>"
   ]
 }

 # Tone
 Skeptical, professional, and grounded. Do not be optimistic. If the ideator says "it's just a simple API," you should explain why the edge cases will kill the timeline.
"""

critique_lawyer = Agent(critique_lawyer_prompt)

data = scrape_arxiv()
response = call_llm(data[0]["summary"], critique_lawyer)

pprint(response)



