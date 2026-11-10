# cloudqa-nl-test-runner

Run a test case written in plain English against a website. An LLM reads the page, decides what to click or type in a real Chromium browser (Playwright), and the tool reports PASS or FAIL.

For the reasoning behind the design and the known limits, see [APPROACH.md](APPROACH.md).

## How it works

- Before each step the tool reads the live page and builds a text view: URL, title, a numbered list of visible interactive elements (links, buttons, inputs, selects and clickable `div`s), and the visible text.
- The LLM gets the test case, the steps so far and that view, and calls exactly one tool: `goto`, `click`, `fill`, `select`, `press`, `wait` or `finish`. It refers to elements by number, never by selector.
- The loop ends when the model calls `finish` with a verdict and a reason that quotes what it saw on the page. Reaching the step limit is a FAIL. An LLM or browser error is an ERROR, not a FAIL.
- Nothing is specific to any site: the only inputs are the test case, the start URL and the LLM settings.
- Every run saves a step log and a final screenshot.

## Requirements

- Python 3.12
- A free Groq API key from https://console.groq.com
- Internet access (for the LLM and the site under test)

## Setup

Windows (PowerShell):

```powershell
git clone https://github.com/thisisfaizanali/cloudqa-nl-test-runner.git
cd cloudqa-nl-test-runner
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
```

macOS / Linux:

```bash
git clone https://github.com/thisisfaizanali/cloudqa-nl-test-runner.git
cd cloudqa-nl-test-runner
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env
```

Then open `.env` and replace `your_groq_key_here` with your Groq key. The other two values can stay as they are.

## Usage

Run from the repository root. On Windows use `.\.venv\Scripts\python.exe` in place of `python` below, on macOS/Linux use `.venv/bin/python` (or activate the venv).

```
python run.py "<test case in plain English>" --url <start URL>
```

| Option | Default | Meaning |
|---|---|---|
| `test_case` | required | The test case, as one quoted string |
| `--url` | required | The page to open first |
| `--max-steps` | 25 | Step limit. Reaching it without a verdict is a FAIL |
| `--headed` | off | Show the browser window |
| `--env-file` | `.env` | File with `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` |

Example (Windows):

```powershell
.\.venv\Scripts\python.exe run.py "Open the Form Authentication page, log in with username tomsmith and password SuperSecretPassword!, and verify the message 'You logged into a secure area!' is shown" --url https://the-internet.herokuapp.com
```

Output (the steps are printed as they run):

```
1. click(ref=34) [link "Form Authentication"] -> ok
2. fill(ref=4, text='tomsmith') [textbox "Username"] -> ok
3. fill(ref=6, text='SuperSecretPassword!') [textbox "Password"] -> ok
4. click(ref=7) [button "Login"] -> ok

RESULT: PASS
REASON: The page displays the text 'You logged into a secure area!' confirming successful login.
STEPS: 5
DURATION: 26.1s
EVIDENCE: runs\20261110-173112
```

`STEPS` counts the model's turns, including the final `finish` call.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | PASS |
| 1 | FAIL (verdict was fail, or the step limit was reached) |
| 2 | ERROR (LLM or browser error, missing environment variable, bad arguments) |

Evidence: each run creates `runs/<timestamp>/` with `log.txt` (test case, every step, verdict and reason) and `final.png` (the page at the end). `runs/` is git-ignored.

## Writing test cases

- Put credentials and data in the sentence. The tool uses only what you give it and invents dummy values for anything else.
- State the expected outcome explicitly: "verify the products page is shown". A test case with no "verify" has nothing to pass or fail on.
- One scenario per test case.
- Start `--url` near the flow (for example the login page), so fewer steps are spent navigating.

## Examples

Real runs with the default Groq setup, headless. Seconds are the `DURATION` the tool printed. Each case ran once.

| Test case | `--url` | Expected | Actual (steps, seconds) |
|---|---|---|---|
| Log in with username standard_user and password secret_sauce and verify the products page is shown | https://www.saucedemo.com | PASS | PASS (4 steps, 6.6 s) |
| Log in with username locked_out_user and password secret_sauce and verify the products page is shown | https://www.saucedemo.com | FAIL (user is locked out) | FAIL (4 steps, 6.9 s): "this user has been locked out" |
| Go to the login page, sign in with email test@example.com and password wrong123, and verify an error message is shown | https://phptravels.net | PASS | PASS (9 steps, 74.4 s): "Invalid Credentials" |
| Open the Form Authentication page, log in with username tomsmith and password SuperSecretPassword!, and verify the message 'You logged into a secure area!' is shown | https://the-internet.herokuapp.com | PASS | PASS (5 steps, 26.1 s) |
| Add a todo item called 'buy milk', then verify the list shows 1 item left | https://demo.playwright.dev/todomvc | PASS | PASS (3 steps, 8.1 s) |
| Add a todo item called 'buy milk', then verify the list shows 3 items left | https://demo.playwright.dev/todomvc | FAIL | FAIL (3 steps, 13.5 s): page shows "1 item left" |

The phptravels case took longer because the first three clicks on "Login" timed out (5 s each) until the model clicked an "I Understand & Continue" button on the page. A phptravels hotel search for Dubai also passed (16 steps, about 4 minutes, slowed by rate-limit retries). Logged-in phptravels flows were not tested, because the demo credentials are only issued after a form that asks for personal details.

## Running the offline tests

No network or API key needed. Uses a local HTML page and Chromium:

```
python -m unittest discover -s tests
```

## Project layout

- `run.py`: command line entry point, writes the run evidence
- `nlrunner/agent.py`: the LLM loop, tool definitions and verdict
- `nlrunner/page_view.py`: page to numbered text, and the browser actions
- `tests/test_page_view.py`: offline tests
- `.env.example`: LLM settings template
