### Phase 1: State Management & Database Foundation

Get the data structures and storage out of the way first. You want zero friction when passing data between the LLMs.

1. **Define the Dataclasses:**
* Create `Signal`, `Idea`, and `Verdict` using Python's `@dataclass`.
* Keep types strict here so you don't have to guess what the scrapers are handing to the LLMs.


2. **Initialize SQLite:**
* Write a `db.py` module with an `init_db()` function.
* Execute the `CREATE TABLE` statements for `ideas` and `seen_signals` using the standard `sqlite3` library.
* Write two helper functions: `is_signal_seen(url_hash)` and `save_verdict(verdict, full_transcript)`.



### Phase 2: The Scraper Layer (The HTTP Pipeline)

Since you already have basic scrapers, wrap them in `httpx` and add the hashing logic.

1. **Implement API Calls:**
* Create a separate function for each source (`scrape_github()`, `scrape_hn()`, etc.) using `httpx.get()`.
* Extract only the required fields defined in your spec.


2. **Deduplication Logic:**
* In the main scraping orchestrator, run each URL through `hashlib.sha256(url.encode()).hexdigest()`.
* Check the hash against the `seen_signals` table. If it exists, drop it. If not, append it to your `list[Signal]` and insert the hash into the DB.


3. **The Signal Batcher:**
* Concatenate the valid `Signal` objects into a single formatted text block (e.g., `Title: ... \n Blurb: ...`) to feed the Ideator.



### Phase 3: The LLM Core & Prompts

This is the engine. Keep the `ollama` wrapper dead simple, but make it robust against malformed JSON.

1. **The Base Call:**
* Implement `call_llm(system_prompt, user_prompt)` exactly as specified.


2. **The JSON Wrapper:**
* Write a `call_llm_json()` wrapper that tries to `json.loads()` the response. If it fails (because Qwen decided to add markdown blocks), strip the ````json` tags and try once more. If it fails twice, throw a handled exception to skip the cycle.


3. **Prompt Dictionary:**
* Store your system prompts in a separate `prompts.py` file. You need: `IDEATOR_PROMPT`, the 5 Round 1 `LAWYER_PROMPTS`, the 5 Round 2 `REBUTTAL_PROMPTS`, and the `JUDGE_PROMPT`.



### Phase 4: The Courtroom Orchestrator (The Main Loop)

This is where the magic happens. Build a single execution function `run_council_cycle(signals)` that processes one idea end-to-end.

1. **Generate the Idea:**
* Pass the batched signals to the Ideator. Extract the JSON into the `Idea` dataclass.


2. **Round 1 (Opening Arguments):**
* Iterate through a dictionary of your 5 lawyers.
* Pass the `Idea` to each lawyer independently.
* Store their JSON responses in a `round1_results` dictionary.


3. **Transcript Assembly:**
* Format a `transcript_so_far` string containing the `Idea` and all 5 arguments from `round1_results`.


4. **Round 2 (Cross Examination):**
* Iterate through the lawyers again. Pass the `transcript_so_far` to each.
* Store their updated scores and rebuttals in a `round2_results` dictionary.


5. **The Verdict:**
* Format the final `full_transcript` (Idea + R1 + R2).
* Pass this to the Judge.
* Parse the Judge's JSON output into the `Verdict` dataclass.



### Phase 5: Routing & CLI

Wrap it all up so you can trigger it cleanly from the terminal.

1. **The Verdict Router:**
* Check the `Verdict` object. If `weighted_score >= 6.5` AND `solo_feasibility >= 5`, call your `save_verdict()` DB function. Otherwise, print a rejection message and move on.


2. **Typer Interface:**
* Build a quick CLI using `typer`.
* Command 1: `python main.py run --cycles 5` (executes the scraper -> orchestrator loop N times).
* Command 2: `python main.py browse` (fetches saved ideas from SQLite and uses `rich` to print a clean table of the high-scoring projects).



Build the DB, plug in the HTTP calls, write the orchestrator loop, and let Ollama argue with itself while you get back to writing C.
