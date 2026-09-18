"""Tests for the converter web UI."""

from __future__ import annotations

import io
import json
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

import hkd2usd


def fake_response(payload: object) -> mock.MagicMock:
    response = mock.MagicMock()
    response.__enter__.return_value = io.StringIO(json.dumps(payload))
    return response


class IndexViewTests(TestCase):
    def setUp(self):
        self.url = reverse("core:index")

    def post(self, **overrides):
        data = {
            "amount": "780",
            "direction": "hkd_to_usd",
            "source": "peg",
            "custom_rate": "",
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_get_renders_the_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HKD")
        self.assertTemplateUsed(response, "core/index.html")

    def test_peg_default_conversion(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "US$100.00")
        self.assertContains(response, "7.8000")
        self.assertContains(response, "peg default")

    def test_custom_rate_is_used(self):
        response = self.post(amount="100", source="custom", custom_rate="8")
        self.assertContains(response, "US$12.50")
        self.assertContains(response, "8.0000")
        self.assertContains(response, "supplied")

    def test_reverse_direction(self):
        response = self.post(amount="100", direction="usd_to_hkd")
        self.assertContains(response, "HK$780.00")
        self.assertContains(response, "USD per HKD")

    def test_commas_and_symbols_are_accepted(self):
        response = self.post(amount="HK$1,560.00")
        self.assertContains(response, "US$200.00")

    def test_invalid_amount_shows_an_error_and_no_result(self):
        response = self.post(amount="banana")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not a number")
        self.assertNotContains(response, "class=\"figure\"")

    def test_zero_amount_is_rejected(self):
        response = self.post(amount="0")
        self.assertContains(response, "greater than zero")

    def test_custom_source_without_rate_shows_an_error(self):
        response = self.post(source="custom", custom_rate="")
        self.assertContains(response, "Enter a rate")

    def test_negative_custom_rate_is_rejected(self):
        response = self.post(source="custom", custom_rate="-7.8")
        self.assertContains(response, "greater than zero")
        self.assertContains(response, "not a number", count=0)

    def test_non_numeric_custom_rate_says_so(self):
        response = self.post(source="custom", custom_rate="seven")
        self.assertContains(response, "is not a number")

    def test_live_rate_is_used_when_provider_answers(self):
        payload = {"result": "success", "rates": {"USD": 0.125}, "time_last_update_utc": "now"}
        with mock.patch.object(hkd2usd, "urlopen", return_value=fake_response(payload)):
            response = self.post(amount="1000", source="live")
        self.assertContains(response, "US$125.00")
        self.assertContains(response, "live")

    def test_live_failure_falls_back_to_peg_and_warns(self):
        with mock.patch.object(hkd2usd, "urlopen", side_effect=OSError("offline")):
            response = self.post(amount="780", source="live")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "US$100.00")
        self.assertContains(response, "using peg default")
        self.assertContains(response, "peg default")


class HistoryTests(TestCase):
    def setUp(self):
        self.url = reverse("core:index")

    def convert(self, amount="780"):
        return self.client.post(
            self.url,
            {"amount": amount, "direction": "hkd_to_usd", "source": "peg", "custom_rate": ""},
        )

    def test_conversions_are_recorded_newest_first(self):
        self.convert("780")
        self.convert("1560")
        history = self.client.session["history"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["amount"], "HK$1,560.00")
        self.assertEqual(history[0]["converted"], "US$200.00")

    def test_history_is_capped(self):
        for _ in range(settings.HISTORY_LIMIT + 5):
            self.convert()
        self.assertEqual(len(self.client.session["history"]), settings.HISTORY_LIMIT)

    def test_failed_conversion_is_not_recorded(self):
        self.client.post(
            self.url,
            {"amount": "nope", "direction": "hkd_to_usd", "source": "peg", "custom_rate": ""},
        )
        self.assertNotIn("history", self.client.session)

    def test_clear_history_empties_the_table(self):
        self.convert()
        response = self.client.post(reverse("core:clear_history"))
        self.assertRedirects(response, self.url)
        self.assertNotIn("history", self.client.session)
        self.assertNotContains(self.client.get(self.url), "Recent conversions")

    def test_clear_history_requires_post(self):
        self.assertEqual(self.client.get(reverse("core:clear_history")).status_code, 405)


class FrontEndContractTests(TestCase):
    """Lock the DOM hooks that core/static/core/app.js depends on.

    The direction buttons convert without a second press of Convert, and the
    result is scrolled into view after that reload. Both are client-side, so no
    server test would otherwise notice a renamed id or a changed input name
    quietly breaking the behaviour.
    """

    def setUp(self):
        self.url = reverse("core:index")

    def convert(self, **overrides):
        data = {
            "amount": "780",
            "direction": "hkd_to_usd",
            "source": "peg",
            "custom_rate": "",
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_page_loads_the_script(self):
        self.assertContains(self.client.get(self.url), "core/app.js")

    def test_amount_input_keeps_its_id(self):
        # The script reads #id_amount to decide whether there is anything to
        # convert before auto-submitting.
        self.assertContains(self.client.get(self.url), 'id="id_amount"')

    def test_direction_is_rendered_as_named_radio_inputs(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="direction"', count=2)

    def test_custom_rate_hooks_are_intact(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="custom-rate-field"')
        self.assertContains(response, 'id="id_custom_rate"')

    def test_result_section_carries_the_scroll_target(self):
        response = self.convert()
        self.assertContains(response, 'id="result"')

    def test_scroll_target_is_absent_without_a_result(self):
        self.assertNotContains(self.client.get(self.url), 'id="result"')

    def test_direction_buttons_submit_the_same_way_the_button_does(self):
        """The auto-submit posts exactly what a Convert press posts."""
        forward = self.convert(direction="hkd_to_usd")
        reverse_ = self.convert(direction="usd_to_hkd")
        self.assertContains(forward, "US$100.00")
        self.assertContains(reverse_, "HK$780.00")
        self.assertContains(reverse_, "USD per HKD")
