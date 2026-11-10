"""Offline tests: a local HTML fixture, no network, no LLM."""
import unittest
from unittest import mock

from playwright.sync_api import sync_playwright

from nlrunner import page_view
from nlrunner.agent import _label
from nlrunner.page_view import do_action, snapshot

_pw = _browser = None


def setUpModule():
    global _pw, _browser
    _pw = sync_playwright().start()
    _browser = _pw.chromium.launch()


def tearDownModule():
    _browser.close()
    _pw.stop()


def load(body):
    page = _browser.new_page()
    page.set_content(f"<html><body>{body}</body></html>")
    return page


def lines(page):
    """Element lines of the snapshot, without the page text."""
    snap = snapshot(page)
    return snap.split("INTERACTIVE ELEMENTS:\n")[1].split("\nVISIBLE TEXT:")[0].splitlines()


class PageViewTests(unittest.TestCase):
    def tearDown(self):
        self.page.close()

    def test_kinds_and_names(self):
        self.page = load("""
            <button>Save</button><a href="/x">Docs</a>
            <label for="u">Username</label><input id="u" type="text">
            <input placeholder="Search">
            <select aria-label="Size"><option>One</option><option selected>Two</option></select>""")
        self.assertEqual(lines(self.page), [
            '[1] button "Save"',
            '[2] link "Docs"',
            '[3] textbox type=text "Username" value=""',
            '[4] textbox type=text "Search" value=""',
            '[5] select "Size" options: One | Two current="Two"',
        ])

    def test_hidden_elements_not_listed(self):
        self.page = load("""
            <input type="hidden" value="x"><button style="display:none">A</button>
            <button style="visibility:hidden">B</button><button>Shown</button>""")
        self.assertEqual(lines(self.page), ['[1] button "Shown"'])

    def test_pointer_div_listed_once(self):
        self.page = load('<div style="cursor:pointer">Open menu <span>now</span></div>')
        self.assertEqual(lines(self.page), ['[1] clickable "Open menu now"'])

    def test_pointer_inside_button_not_listed(self):
        self.page = load('<button>Go <span style="cursor:pointer">here</span></button>')
        self.assertEqual(lines(self.page), ['[1] button "Go here"'])

    def test_refs_in_document_order_with_attribute(self):
        self.page = load('<button>A</button><a href="#">B</a><input placeholder="C"><button>D</button>')
        ls = lines(self.page)
        self.assertEqual([l.split("]")[0] for l in ls], ["[1", "[2", "[3", "[4"])
        for n in range(1, 5):
            self.assertEqual(self.page.locator(f'[data-nlr="{n}"]').count(), 1)
        self.assertEqual(self.page.locator("[data-nlr]").evaluate_all("els => els.map(e => e.textContent)"),
                         ["A", "B", "", "D"])

    def test_actions(self):
        self.page = load("""<input placeholder="Name"><button onclick="document.getElementById('o').textContent='Done!'">Go</button>
            <p id="o"></p>""")
        snapshot(self.page)
        self.assertEqual(do_action(self.page, "fill", {"ref": 1, "text": "Ada"}), "ok")
        self.assertEqual(self.page.input_value('[data-nlr="1"]'), "Ada")
        self.assertEqual(do_action(self.page, "click", {"ref": 2}), "ok")
        self.assertIn("Done!", snapshot(self.page).split("VISIBLE TEXT:")[1])
        with mock.patch.object(page_view, "TIMEOUT", 500):
            self.assertTrue(do_action(self.page, "click", {"ref": 99}).startswith("ERROR:"))


class LabelTests(unittest.TestCase):
    SNAP = '[1] button "Save"\n[2] textbox type=text "Username" value="x"'

    def test_label(self):
        self.assertEqual(_label(self.SNAP, 1), ' [button "Save"]')
        self.assertEqual(_label(self.SNAP, 2), ' [textbox "Username"]')
        self.assertEqual(_label(self.SNAP, 3), "")


if __name__ == "__main__":
    unittest.main()
