"""Views for the converter UI."""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

import hkd2usd

from .forms import ConversionForm

HISTORY_KEY = "history"


def index(request):
    """Render the converter, and convert on submit."""
    form = ConversionForm(request.POST or None)
    result = None

    if request.method == "POST" and form.is_valid():
        rate, warnings = form.resolve_rate()
        reverse = form.reverse
        amount = form.cleaned_data["amount"]
        converted = hkd2usd.convert(amount, rate, reverse)

        source_symbol, target_symbol = ("US$", "HK$") if reverse else ("HK$", "US$")
        result = {
            "amount": hkd2usd.money(amount, source_symbol),
            "converted": hkd2usd.money(converted, target_symbol),
            "rate": rate.hkd_per_usd_fmt,
            "rate_quote": "USD per HKD" if reverse else "HKD per USD",
            "source": rate.source,
            "as_of": rate.as_of,
            "warnings": warnings,
        }
        _remember(request, result, reverse)

    return render(
        request,
        "core/index.html",
        {
            "form": form,
            "result": result,
            "history": request.session.get(HISTORY_KEY, []),
        },
    )


@require_POST
def clear_history(request):
    request.session.pop(HISTORY_KEY, None)
    return redirect("core:index")


def _remember(request, result: dict, reverse: bool) -> None:
    """Push a conversion onto the session history, newest first."""
    entry = {
        "amount": result["amount"],
        "converted": result["converted"],
        "rate": result["rate"],
        "source": result["source"],
        "direction": "USD to HKD" if reverse else "HKD to USD",
        "at": timezone.localtime().strftime("%d %b %Y, %H:%M"),
    }
    history = [entry, *request.session.get(HISTORY_KEY, [])][: settings.HISTORY_LIMIT]
    request.session[HISTORY_KEY] = history
