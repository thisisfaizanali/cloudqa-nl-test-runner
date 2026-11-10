"""LLM loop: one fresh request per step, the model picks one browser tool call."""
import json
import os
import re
from dataclasses import dataclass

import openai
from openai import OpenAI
from playwright.sync_api import Error as PlaywrightError, sync_playwright

from .page_view import do_action, snapshot

SYSTEM_PROMPT = """You are a QA tester driving a real browser to execute one test case. \
Each turn you get the test case, the steps taken so far, and the current page.
Rules:
- Call exactly one tool per turn.
- Use element numbers from the CURRENT page only.
- Use only credentials and data given in the test case; for other required inputs use realistic dummy values.
- Close popups, notices or cookie banners that block the page.
- When every expected outcome in the test case is visible on the current page, call finish with passed=true and quote the evidence from the page in reason.
- If an expected outcome is clearly contradicted, or a required step is impossible after reasonable attempts, call finish with passed=false and explain.
- Never pass a test whose expected outcome you have not seen."""


def _tool(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required}}}


_REF = {"type": "integer", "description": "element number from the current page"}
TOOLS = [
    _tool("goto", "Open a URL.", {"url": {"type": "string"}}, ["url"]),
    _tool("click", "Click an element.", {"ref": _REF}, ["ref"]),
    _tool("fill", "Type text into an input, replacing its content.",
          {"ref": _REF, "text": {"type": "string"}}, ["ref", "text"]),
    _tool("select", "Choose an option in a select element.",
          {"ref": _REF, "option": {"type": "string", "description": "option label"}}, ["ref", "option"]),
    _tool("press", "Press a key, on an element if ref is given.",
          {"key": {"type": "string", "description": "e.g. Enter, Tab, Escape"}, "ref": _REF}, ["key"]),
    _tool("wait", "Wait for the page to update (max 5 seconds).", {"seconds": {"type": "number"}}, ["seconds"]),
    _tool("finish", "End the test with a verdict.",
          {"passed": {"type": "boolean"}, "reason": {"type": "string"}}, ["passed", "reason"]),
]


@dataclass
class Result:
    status: str  # "PASS" | "FAIL" | "ERROR"
    reason: str
    steps: int


def _label(snap, ref):
    """Kind and name of element `ref` as shown in the snapshot, for the history line."""
    m = re.search(rf'^\[{ref}\] (\S+) (?:type=\S+ )?(".*?")(?= value=| options:| checked=| disabled|$)', snap, re.M)
    return f" [{m.group(1)} {m.group(2)}]" if m else ""


def run_test(test_case: str, url: str, max_steps: int = 25, headed: bool = False) -> Result:
    client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"],
                    max_retries=6, timeout=60)
    model = os.environ["LLM_MODEL"]
    history, done, i = [], [], 0  # done: (name, args) of executed actions, for the repeat guard
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(url)
            for i in range(1, max_steps + 1):
                snap = snapshot(page)
                user = (f"TEST CASE:\n{test_case}\n\nSTEPS SO FAR:\n{chr(10).join(history) or 'none'}"
                        f"\n\nCURRENT PAGE (step {i} of {max_steps}):\n{snap}")
                resp = client.chat.completions.create(
                    model=model, tools=TOOLS, tool_choice="required", temperature=0,
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}])
                calls = resp.choices[0].message.tool_calls if resp.choices else None
                if not calls:
                    history.append(f"{i}. (model returned no tool call)")
                    print(history[-1])
                    continue
                name, raw = calls[0].function.name, calls[0].function.arguments
                try:
                    args = json.loads(raw or "{}")
                    if not isinstance(args, dict):
                        raise ValueError("arguments are not an object")
                except ValueError:
                    history.append(f"{i}. {name}(invalid JSON arguments)")
                    print(history[-1])
                    continue
                if name == "finish":
                    return Result("PASS" if args.get("passed") in (True, "true") else "FAIL",
                                  str(args.get("reason", "")), i)
                label = _label(snap, args["ref"]) if str(args.get("ref", "")).isdigit() else ""
                shown = ", ".join(f"{k}={v!r}" for k, v in args.items())
                history.append(f"{i}. {name}({shown}){label} -> {do_action(page, name, args)}")
                print(history[-1])
                done.append((name, json.dumps(args, sort_keys=True)))
                if len(done) >= 3 and done[-1] == done[-2] == done[-3]:
                    history.append("   note: this exact action was repeated 3 times; the page is probably "
                                   "not responding to it. Try a different element or approach, or call finish.")
                    print(history[-1])
                page = context.pages[-1]
            return Result("FAIL", f"step limit of {max_steps} reached without a verdict", max_steps)
        except openai.APIError as e:
            return Result("ERROR", f"model unavailable: {str(e)[:200]}", i)
        except PlaywrightError as e:
            return Result("ERROR", f"browser error: {(str(e).strip().splitlines() or [''])[0][:200]}", i)
        finally:
            browser.close()
