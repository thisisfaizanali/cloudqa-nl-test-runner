# Approach and limitations

## Approach

**Agent loop, not a generated script.** The tool does not ask the model to write a Playwright script up front. It does not know the page, so a script would guess at selectors and break on the first surprise. Instead the model acts one step at a time and reacts to what the page shows, including popups, validation errors and slow loads.

**Numbered element list, not raw HTML or screenshots.** Before each step the tool reads the live page and builds a short text view: the URL, the title, every visible interactive element as `[7] button "Login"`, and the first 2500 characters of visible text. The model answers with an element number, so it never writes a selector. This view is a few thousand characters, which fits a free-tier token budget, needs no vision model, and is the same for any site.

**One fresh request per step.** Each step sends only the test case, a one-line-per-step history and the current page. Nothing accumulates, so token use stays flat however long the run is. The model has seven tools: `goto`, `click`, `fill`, `select`, `press`, `wait` and `finish`. It must call exactly one each turn (`tool_choice` is required, temperature 0).

**The verdict never passes by default.** The run ends only when the model calls `finish(passed, reason)`. The prompt tells it to pass only when it has seen every expected outcome on the current page, and to quote that evidence. Reaching the step limit (25 by default) is a FAIL. A model or browser error is reported as ERROR (exit code 2), not FAIL, so an outage is never mistaken for a failing test.

**Why Groq and Gemini.** Both have a free tier, an OpenAI-compatible API and tool calling, so the tool is built on the `openai` SDK and takes the endpoint, key and model from three environment variables. Switching provider is one env file (`--env-file`). Groq with `openai/gpt-oss-120b` is fast but has a daily cap of 200,000 tokens. Gemini was first tried with `gemini-2.5-flash` (retired, returns 404 for new keys) and `gemini-3.8-flash` (timed out on every request), then `gemini-3.5-flash` worked.

## Design decisions

- **`cursor: pointer` detection.** The first version only listed semantic elements (links, buttons, inputs). The phptravels search widgets are plain `div`s, so they were invisible. A second pass now adds the outermost visible element with a pointer cursor that is not inside or around an element already listed, shown as `clickable`.
- **Repeat guard.** After the same action three times in a row, a note is added to the history telling the model that, unless the test case asks for the repeat, the page is probably not responding, and to try something else or finish.
- **Steps as written.** The prompt forbids actions beyond the stated steps, after a final audit caught the model clicking an extra time to make an expected outcome true.
- **Rate limits.** The SDK retries 429 and 5xx responses up to 6 times with backoff. This is why a long run on the free tier can take minutes.
- **UTF-8 console.** Page text can contain characters the Windows console codepage cannot print, so output is reconfigured to UTF-8.
- **Evidence folder.** Every run writes `runs/<timestamp>/log.txt` (test case, steps, verdict, reason) and `final.png`, so a verdict can be checked afterwards.

## Limitations

- The verdict is an LLM judgment. It can be wrong in both directions (a false PASS or a false FAIL), and results can differ between runs of the same test case.
- Free-tier rate limits make long flows slow. A 16-step hotel search on phptravels took about 4 minutes.
- The Groq free tier also has a daily token cap (200,000 tokens per day for openai/gpt-oss-120b when tested). A day of heavy testing used it up, and runs then return ERROR (exit 2) until the quota resets.
- Gemini's free tier allows few requests per day per model. `gemini-3.5-flash` ran out after about 30 requests (roughly 6 test runs), so only four examples were run on it.
- The page view is capped at 120 elements and 2500 characters of text, and there is no scroll tool. Content far down a long page can be missed.
- Not supported: iframes, shadow DOM, canvas, file upload, drag and drop, menus that open only on hover, CAPTCHA and 2FA.
- Clickable detection is a heuristic. The extra pass checks every element against its neighbours, so it gets slow (roughly quadratic) on very large pages.
- One test case per run. There is no suite runner.
- Logged-in phptravels flows were not tested, because the demo credentials are only issued after a form asking for personal details. Tested phptravels flows: a wrong-password login (PASS) and a hotel search for Dubai (PASS).
- Credentials written in a test case appear in the console output and in the `runs/` logs. `runs/` is git-ignored.
- A `select` with no label is named by its option text, which can be confusing.
- If Chromium fails to launch (for example, browsers not installed), the error is a raw Python traceback, not an ERROR result.
- The step rule is enforced by the prompt, not by code, so a model can still drift from the written steps.
- Only Groq (`openai/gpt-oss-120b`) and Gemini (`gemini-3.5-flash`) were tested. Other providers and models may behave differently.

## What I would do next

- Add scroll and find-text tools so content below the page view cap can be reached.
- Add a suite runner that reads many test cases from a file and prints a summary table.
- Retry a FAIL once, to separate a flaky run from a real failure.
- Record a Playwright trace or video per run, not just the final screenshot.
- Support iframes.
