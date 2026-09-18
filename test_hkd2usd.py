#!/usr/bin/env python3
"""Tests for hkd2usd.py. Run with: python -m unittest -v"""

from __future__ import annotations

import argparse
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import hkd2usd
from hkd2usd import PEG_DEFAULT_HKD_PER_USD, Rate, RateError


def fake_response(payload: object) -> mock.MagicMock:
    """Stand-in for the urlopen context manager returning a JSON body."""
    response = mock.MagicMock()
    response.__enter__.return_value = io.StringIO(json.dumps(payload))
    return response


class ParseAmountTests(unittest.TestCase):
    def test_plain_numbers(self):
        self.assertEqual(hkd2usd.parse_amount("1000"), 1000.0)
        self.assertEqual(hkd2usd.parse_amount(" 12.5 "), 12.5)

    def test_separators_and_symbols(self):
        for text in ("1,500.50", "HK$1,500.50", "hkd 1500.50", "$1,500.50"):
            self.assertEqual(hkd2usd.parse_amount(text), 1500.50, text)

    def test_rejects_garbage_and_negatives(self):
        for text in ("abc", "", "1,00x", "-5"):
            with self.assertRaises(argparse.ArgumentTypeError, msg=text):
                hkd2usd.parse_amount(text)


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self.rate = Rate(7.80, "peg default")

    def test_hkd_to_usd(self):
        self.assertAlmostEqual(hkd2usd.convert(780.0, self.rate), 100.0)
        self.assertAlmostEqual(hkd2usd.convert(1000.0, self.rate), 128.205128, places=6)

    def test_usd_to_hkd(self):
        self.assertAlmostEqual(hkd2usd.convert(100.0, self.rate, reverse=True), 780.0)

    def test_zero(self):
        self.assertEqual(hkd2usd.convert(0.0, self.rate), 0.0)


class MoneyFormatTests(unittest.TestCase):
    def test_thousands_and_cents(self):
        self.assertEqual(hkd2usd.money(1234567.891, "HK$"), "HK$1,234,567.89")
        self.assertEqual(hkd2usd.money(0, "US$"), "US$0.00")


class FetchLiveRateTests(unittest.TestCase):
    def test_success_inverts_the_provider_rate(self):
        payload = {"result": "success", "rates": {"USD": 0.1282}, "time_last_update_utc": "X"}
        with mock.patch.object(hkd2usd, "urlopen", return_value=fake_response(payload)):
            rate = hkd2usd.fetch_live_rate()
        self.assertAlmostEqual(rate.hkd_per_usd, 1 / 0.1282, places=6)
        self.assertEqual(rate.source, "live")
        self.assertEqual(rate.as_of, "X")

    def test_unreachable_provider_raises_rate_error(self):
        with mock.patch.object(hkd2usd, "urlopen", side_effect=OSError("no route to host")):
            with self.assertRaises(RateError):
                hkd2usd.fetch_live_rate()

    def test_provider_error_payload_raises_rate_error(self):
        payload = {"result": "error", "error-type": "quota-exceeded"}
        with mock.patch.object(hkd2usd, "urlopen", return_value=fake_response(payload)):
            with self.assertRaises(RateError):
                hkd2usd.fetch_live_rate()

    def test_missing_usd_rate_raises_rate_error(self):
        payload = {"result": "success", "rates": {"EUR": 0.11}}
        with mock.patch.object(hkd2usd, "urlopen", return_value=fake_response(payload)):
            with self.assertRaises(RateError):
                hkd2usd.fetch_live_rate()

    def test_implausible_rate_is_rejected(self):
        # A provider reporting HKD per USD under the USD key would give ~7.8.
        payload = {"result": "success", "rates": {"USD": 7.8}}
        with mock.patch.object(hkd2usd, "urlopen", return_value=fake_response(payload)):
            with self.assertRaises(RateError):
                hkd2usd.fetch_live_rate()


class MainTests(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = hkd2usd.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_defaults_to_peg_rate(self):
        code, out, err = self.run_main(["780"])
        self.assertEqual(code, 0)
        self.assertIn("HK$780.00  ->  US$100.00", out)
        self.assertIn("source: peg default", out)
        self.assertEqual(err, "")

    def test_explicit_rate(self):
        code, out, _ = self.run_main(["100", "--rate", "8"])
        self.assertEqual(code, 0)
        self.assertIn("US$12.50", out)
        self.assertIn("source: supplied", out)

    def test_reverse_direction(self):
        _, out, _ = self.run_main(["100", "--reverse"])
        self.assertIn("US$100.00  ->  HK$780.00", out)
        self.assertIn("USD per HKD", out)

    def test_multiple_amounts_reuse_one_rate(self):
        _, out, _ = self.run_main(["780", "1560", "--rate", "7.8"])
        self.assertIn("US$100.00", out)
        self.assertIn("US$200.00", out)
        self.assertEqual(out.count("rate 7.8000"), 1)

    def test_json_output(self):
        _, out, _ = self.run_main(["780", "--rate", "7.8", "--json"])
        payload = json.loads(out)
        self.assertEqual(payload["source"], "supplied")
        self.assertEqual(payload["direction"], "HKD->USD")
        self.assertAlmostEqual(payload["results"][0]["output"], 100.0)

    def test_live_failure_falls_back_to_peg_with_warning(self):
        with mock.patch.object(hkd2usd, "urlopen", side_effect=OSError("offline")):
            code, out, err = self.run_main(["780", "--live"])
        self.assertEqual(code, 0)
        self.assertIn("source: peg default", out)
        self.assertIn("warning: live rate unavailable", err)

    def test_live_success_is_used(self):
        payload = {"result": "success", "rates": {"USD": 0.125}}
        with mock.patch.object(hkd2usd, "urlopen", return_value=fake_response(payload)):
            _, out, err = self.run_main(["1000", "--live"])
        self.assertIn("US$125.00", out)
        self.assertIn("source: live", out)
        self.assertEqual(err, "")

    def test_reads_amounts_from_stdin_when_none_given(self):
        fake_stdin = io.StringIO("780\n1560\n")
        with mock.patch.object(hkd2usd.sys, "stdin", fake_stdin):
            code, out, _ = self.run_main([])
        self.assertEqual(code, 0)
        self.assertIn("US$100.00", out)
        self.assertIn("US$200.00", out)

    def test_no_amounts_and_no_stdin_errors(self):
        tty_stdin = mock.MagicMock()
        tty_stdin.isatty.return_value = True
        with mock.patch.object(hkd2usd.sys, "stdin", tty_stdin):
            with self.assertRaises(SystemExit) as ctx:
                self.run_main([])
        self.assertIn("at least one amount", str(ctx.exception))

    def test_non_positive_rate_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.run_main(["100", "--rate", "0"])


class PegDefaultTests(unittest.TestCase):
    def test_midpoint_sits_inside_the_peg_band(self):
        self.assertEqual(PEG_DEFAULT_HKD_PER_USD, 7.80)
        self.assertTrue(7.75 <= PEG_DEFAULT_HKD_PER_USD <= 7.85)


if __name__ == "__main__":
    unittest.main()
