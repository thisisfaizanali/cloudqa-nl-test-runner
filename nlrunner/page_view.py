"""Turn a live page into numbered text the model can read, and act on those numbers."""
from playwright.sync_api import Error as PlaywrightError

MAX_ELEMENTS = 120
MAX_TEXT_CHARS = 2500
TIMEOUT = 5000

SNAPSHOT_JS = r"""
([maxEl, maxText]) => {
  document.querySelectorAll('[data-nlr]').forEach(e => e.removeAttribute('data-nlr'));
  const SEL = 'a[href], button, input, select, textarea, summary, [role=button], [role=link], ' +
    '[role=checkbox], [role=radio], [role=tab], [role=menuitem], [role=option], [role=combobox], ' +
    '[role=switch], [onclick], [contenteditable=""], [contenteditable="true"]';
  const clean = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const visible = el => {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden';
  };
  const kindOf = el => {
    const role = el.getAttribute('role');
    if (role) return role;
    const t = el.tagName.toLowerCase(), ty = (el.type || '').toLowerCase();
    if (t === 'a') return 'link';
    if (t === 'button') return 'button';
    if (t === 'select') return 'select';
    if (t === 'textarea' || el.isContentEditable) return 'textbox';
    if (t === 'input') {
      if (ty === 'checkbox' || ty === 'radio') return ty;
      if (['button', 'submit', 'reset', 'image'].includes(ty)) return 'button';
      return 'textbox';
    }
    return t;
  };
  const nameOf = el => {
    const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/);
    const by = ids.map(i => (document.getElementById(i) || {}).textContent || '').join(' ');
    const img = el.querySelector('img[alt]');
    const cands = [el.getAttribute('aria-label'), by,
      Array.from(el.labels || []).map(l => l.innerText).join(' '),
      el.getAttribute('placeholder'), el.getAttribute('title'), img && img.alt,
      el.innerText, el.value];
    for (const c of cands) { const v = clean(c, 80); if (v) return v; }
    return '';
  };
  const out = []; let truncated = false;
  for (const el of document.querySelectorAll(SEL)) {
    if (el.matches('input[type=hidden]') || !visible(el)) continue;
    if (out.length >= maxEl) { truncated = true; break; }
    const ref = out.length + 1;
    el.setAttribute('data-nlr', ref);
    const kind = kindOf(el), tag = el.tagName;
    const item = { ref, kind, name: nameOf(el), disabled: !!el.disabled };
    if (tag === 'INPUT' && kind !== 'checkbox' && kind !== 'radio') item.type = el.type;
    if (tag === 'SELECT') {
      const opts = Array.from(el.options).map(o => clean(o.label || o.text, 40));
      item.options = opts.slice(0, 15);
      item.more = Math.max(0, opts.length - 15);
      const sel = el.selectedOptions[0];
      item.value = sel ? clean(sel.label || sel.text, 40) : '';
    } else if (kind === 'textbox' && (tag === 'INPUT' || tag === 'TEXTAREA')) {
      item.value = clean(el.value, 40);
    }
    if (el.type === 'checkbox' || el.type === 'radio') item.checked = el.checked;
    else if (el.getAttribute('aria-checked')) item.checked = el.getAttribute('aria-checked') === 'true';
    out.push(item);
  }
  return { items: out, truncated, text: clean(document.body.innerText, maxText) };
}
"""


def _line(e):
    s = f'[{e["ref"]}] {e["kind"]}'
    if e.get("type"):
        s += f' type={e["type"]}'
    s += f' "{e["name"]}"'
    if "options" in e:
        s += " options: " + " | ".join(e["options"]) + (f' (+{e["more"]} more)' if e["more"] else "")
        s += f' current="{e["value"]}"'
    elif "value" in e:
        s += f' value="{e["value"]}"'
    if "checked" in e:
        s += f' checked={str(e["checked"]).lower()}'
    return s + (" disabled" if e["disabled"] else "")


def snapshot(page) -> str:
    for attempt in (1, 2):
        try:
            data = page.evaluate(SNAPSHOT_JS, [MAX_ELEMENTS, MAX_TEXT_CHARS])
            title = page.title()
            break
        except PlaywrightError:  # page was navigating under us
            if attempt == 2:
                raise
            page.wait_for_timeout(1000)
    lines = [_line(e) for e in data["items"]]
    if data["truncated"]:
        lines.append("... more elements not shown")
    return (f"URL: {page.url}\nTITLE: {title}\nINTERACTIVE ELEMENTS:\n" + "\n".join(lines)
            + f"\nVISIBLE TEXT:\n{data['text']}")


def do_action(page, name, args) -> str:
    """Run one action. Returns "ok" or "ERROR: ..."; never raises for action failures."""
    try:
        if name == "goto":
            page.goto(args["url"], timeout=TIMEOUT)
        elif name == "wait":
            page.wait_for_timeout(min(float(args["seconds"]), 5) * 1000)
        elif name == "press" and "ref" not in args:
            page.keyboard.press(args["key"])
        elif name in ("click", "fill", "select", "press"):
            loc = page.locator(f'[data-nlr="{int(args["ref"])}"]')
            if name == "click":
                loc.click(timeout=TIMEOUT)
            elif name == "fill":
                loc.fill(args["text"], timeout=TIMEOUT)
            elif name == "press":
                loc.press(args["key"], timeout=TIMEOUT)
            else:
                try:
                    loc.select_option(label=args["option"], timeout=TIMEOUT)
                except PlaywrightError:
                    loc.select_option(value=args["option"], timeout=TIMEOUT)
        else:
            return f"ERROR: unknown action {name}"
        result = "ok"
    except PlaywrightError as e:
        result = "ERROR: " + (str(e).strip().splitlines() or [type(e).__name__])[0][:200]
    except (KeyError, TypeError, ValueError) as e:
        result = f"ERROR: bad arguments for {name} ({type(e).__name__}: {e})"[:200]
    try:
        page.wait_for_load_state("load", timeout=TIMEOUT)
    except PlaywrightError:
        pass
    page.wait_for_timeout(500)
    return result
