"""Tests for the standalone hkd2usd.html entry point.

The page has to run with no server and no install, so it carries its own
JavaScript copy of the conversion rules. That copy is the risk: the page could
stay working while quietly disagreeing with hkd2usd.py, which remains the
reference implementation behind the command line and the Django page.

These tests guard the two ways that promise breaks silently -- the file ceasing
to be self-contained, and its constants drifting away from the Python side.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import hkd2usd

PAGE = Path(__file__).resolve().parent / "hkd2usd.html"


def js_constant(html: str, name: str) -> str | None:
    """Read a `const NAME = ...` declaration out of the page's script."""
    match = re.search(rf"const\s+{name}\s*=\s*([^;]+);", html)
    if match is None:
        return None
    return match.group(1).strip().strip('"')


class StandalonePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PAGE.exists():
            raise AssertionError(f"{PAGE} is missing")
        cls.html = PAGE.read_text(encoding="utf-8")

    def test_page_is_not_empty_and_is_html(self):
        self.assertGreater(len(self.html), 2000)
        self.assertIn("<!DOCTYPE html>", self.html)
        self.assertIn("</html>", self.html)

    def test_styles_and_script_are_inline(self):
        # Self-contained means no requests for anything except the rate API.
        self.assertIsNone(
            re.search(r"<script[^>]*\ssrc=", self.html, re.IGNORECASE),
            "the page must not load an external script",
        )
        self.assertIsNone(
            re.search(r"<link[^>]*stylesheet", self.html, re.IGNORECASE),
            "the page must not link an external stylesheet",
        )
        self.assertNotIn("@import", self.html)
        self.assertIn("<style>", self.html)
        self.assertIn("<script>", self.html)

    def test_loads_nothing_from_the_local_filesystem(self):
        self.assertNotIn("file://", self.html)
        self.assertIsNone(re.search(r'\ssrc="(?!data:)', self.html))

    def test_peg_default_matches_the_python_core(self):
        declared = js_constant(self.html, "PEG_DEFAULT_HKD_PER_USD")
        self.assertIsNotNone(declared, "the page must declare its own peg default")
        self.assertEqual(float(declared), hkd2usd.PEG_DEFAULT_HKD_PER_USD)

    def test_provider_url_matches_the_python_core(self):
        self.assertEqual(js_constant(self.html, "API_URL"), hkd2usd.API_URL)

    def test_offers_the_same_directions_as_the_web_form(self):
        for value in ("hkd_to_usd", "usd_to_hkd"):
            self.assertIn(f'name="direction" value="{value}"', self.html)

    def test_offers_the_same_rate_sources_as_the_web_form(self):
        for value in ("peg", "live", "custom"):
            self.assertIn(f'name="source" value="{value}"', self.html)

    def test_keeps_the_implausible_rate_guard(self):
        # The band that stops a provider reporting HKD per USD under the USD key
        # from showing a figure roughly 7.8x wrong. Presence check only: the
        # Python side owns the exact numbers.
        self.assertIn("0.05", self.html)
        self.assertIn("0.5", self.html)

    def test_falls_back_rather_than_failing_without_a_live_rate(self):
        self.assertIn("using the peg default", self.html)

    def test_direction_change_converts_without_a_second_press(self):
        # Matches the Django page: flipping direction reconverts on its own.
        self.assertIn('input[name="direction"]', self.html)


if __name__ == "__main__":
    unittest.main()
