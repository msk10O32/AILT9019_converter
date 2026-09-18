"""Form for the converter UI.

Amount parsing and rate resolution are delegated to hkd2usd.py so the web page
and the command-line app cannot drift apart on what a valid amount is or which
rate source wins.
"""

from __future__ import annotations

import argparse

from django import forms
from django.conf import settings

import hkd2usd

DIRECTION_CHOICES = [
    ("hkd_to_usd", "HKD to USD"),
    ("usd_to_hkd", "USD to HKD"),
]

SOURCE_CHOICES = [
    ("peg", "Peg default (7.80)"),
    ("live", "Live market rate"),
    ("custom", "Custom rate"),
]


class ConversionForm(forms.Form):
    amount = forms.CharField(
        label="Amount",
        max_length=32,
        widget=forms.TextInput(
            attrs={"placeholder": "1000", "autofocus": True, "inputmode": "decimal"}
        ),
    )
    direction = forms.ChoiceField(
        label="Direction", choices=DIRECTION_CHOICES, initial="hkd_to_usd", widget=forms.RadioSelect
    )
    source = forms.ChoiceField(
        label="Rate source", choices=SOURCE_CHOICES, initial="peg", widget=forms.RadioSelect
    )
    custom_rate = forms.CharField(
        label="Custom rate (HKD per USD)",
        required=False,
        max_length=32,
        widget=forms.TextInput(attrs={"placeholder": "7.85"}),
        help_text="Only used when the rate source is set to Custom.",
    )

    def clean_amount(self) -> float:
        raw = self.cleaned_data["amount"]
        try:
            amount = hkd2usd.parse_amount(raw)
        except argparse.ArgumentTypeError as exc:
            raise forms.ValidationError(f"{exc}. Try something like 1000 or 1,500.50.") from None
        if amount == 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        return amount

    def clean_custom_rate(self) -> float | None:
        raw = (self.cleaned_data.get("custom_rate") or "").strip()
        if not raw:
            return None
        # Parsed directly rather than via hkd2usd.parse_amount: that helper
        # rejects negatives with an "amount" phrasing, which would report a
        # negative rate as "not a number" and mislead the user.
        try:
            rate = float(raw.replace(",", ""))
        except ValueError:
            raise forms.ValidationError(f"{raw!r} is not a number.") from None
        if rate <= 0:
            raise forms.ValidationError("The rate must be greater than zero.")
        return rate

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("source") == "custom" and cleaned.get("custom_rate") is None:
            self.add_error("custom_rate", "Enter a rate, or pick a different rate source.")
        return cleaned

    def resolve_rate(self) -> tuple[hkd2usd.Rate, list[str]]:
        """Resolve the rate exactly as the CLI does, using its priority rules."""
        options = argparse.Namespace(
            rate=self.cleaned_data.get("custom_rate"),
            live=self.cleaned_data.get("source") == "live",
            timeout=settings.LIVE_RATE_TIMEOUT,
        )
        return hkd2usd.resolve_rate(options)

    @property
    def reverse(self) -> bool:
        return self.cleaned_data.get("direction") == "usd_to_hkd"
