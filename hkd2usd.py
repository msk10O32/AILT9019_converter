#!/usr/bin/env python3
"""Lightweight Hong Kong dollar -> US dollar converter.

The exchange rate comes from the first source that is available:

  1. ``--rate``      a rate you supply yourself (HKD per USD)
  2. ``--live``      the current market rate from open.er-api.com (no API key)
  3. built-in        the 7.80 midpoint of the HKD peg band

Usage:
    python hkd2usd.py 1000
    python hkd2usd.py 1000 2500 --live
    python hkd2usd.py --rate 7.85 "1,500.50"
    python hkd2usd.py 100 --reverse
    echo 1000 | python hkd2usd.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Iterable, Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen

# The HKD has been pegged to the USD in a 7.75-7.85 band since 2005, so the
# midpoint is a serviceable offline stand-in for the real rate.
PEG_DEFAULT_HKD_PER_USD = 7.80

API_URL = "https://open.er-api.com/v6/latest/HKD"
USER_AGENT = "hkd2usd/1.0 (+stdlib urllib)"


class RateError(RuntimeError):
    """Raised when a live rate cannot be retrieved or trusted."""


@dataclass(frozen=True)
class Rate:
    """A conversion rate, quoted as HKD per USD like the peg band."""

    hkd_per_usd: float
    source: str
    as_of: str | None = None

    @property
    def hkd_per_usd_fmt(self) -> str:
        return f"{self.hkd_per_usd:.4f}"


def fetch_live_rate(timeout: float = 5.0) -> Rate:
    """Fetch the current rate from open.er-api.com.

    Raises RateError if the provider is unreachable or answers with something
    that is not a plausible HKD/USD rate.
    """
    request = Request(API_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (URLError, OSError, ValueError) as exc:
        raise RateError(f"{API_URL} unreachable: {exc}") from exc

    if payload.get("result") != "success":
        reason = payload.get("error-type") or payload.get("result")
        raise RateError(f"provider refused the request: {reason}")

    try:
        usd_per_hkd = float(payload["rates"]["USD"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RateError("provider response carried no usable USD rate") from exc

    # Rough guard against a unit mix-up (USD per HKD vs HKD per USD) or a
    # malformed payload: one HKD is worth a small fraction of one USD.
    if not 0.05 < usd_per_hkd < 0.5:
        raise RateError(f"implausible rate from provider: {usd_per_hkd} USD per HKD")

    return Rate(1.0 / usd_per_hkd, "live", payload.get("time_last_update_utc"))


def parse_amount(text: str) -> float:
    """Parse a user-supplied amount, tolerating commas and currency symbols."""
    upper = text.strip().upper()
    for prefix in ("HK$", "US$", "HKD", "USD", "$"):
        if upper.startswith(prefix):
            upper = upper[len(prefix) :].strip()
            break

    try:
        value = float(upper.replace(",", ""))
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError(f"amount cannot be negative: {text!r}")
    return value


def convert(amount: float, rate: Rate, reverse: bool = False) -> float:
    """Convert amount, HKD -> USD normally and USD -> HKD when reversed."""
    if reverse:
        return amount * rate.hkd_per_usd
    return amount / rate.hkd_per_usd


def money(value: float, symbol: str) -> str:
    return f"{symbol}{value:,.2f}"


def resolve_rate(args: argparse.Namespace) -> tuple[Rate, list[str]]:
    """Pick a rate, returning it alongside any warnings worth showing."""
    if args.rate is not None:
        return Rate(args.rate, "supplied"), []
    if args.live:
        try:
            return fetch_live_rate(args.timeout), []
        except RateError as exc:
            warning = f"live rate unavailable ({exc}); using peg default"
            return Rate(PEG_DEFAULT_HKD_PER_USD, "peg default"), [warning]
    return Rate(PEG_DEFAULT_HKD_PER_USD, "peg default"), []


def collect_amounts(cli_amounts: Sequence[float]) -> list[float]:
    """Fall back to reading whitespace-separated amounts from stdin."""
    if cli_amounts:
        return list(cli_amounts)
    if sys.stdin is None or getattr(sys.stdin, "isatty", lambda: True)():
        raise SystemExit("error: give at least one amount, e.g. `hkd2usd 1000`")

    amounts = []
    for token in sys.stdin.read().split():
        try:
            amounts.append(parse_amount(token))
        except argparse.ArgumentTypeError as exc:
            raise SystemExit(f"error: {exc}") from None
    if not amounts:
        raise SystemExit("error: no amounts found on stdin")
    return amounts


def render_text(amounts: Iterable[float], rate: Rate, reverse: bool) -> str:
    src, dst = ("US$", "HK$") if reverse else ("HK$", "US$")
    lines = []
    for amount in amounts:
        lines.append(f"{money(amount, src)}  ->  {money(convert(amount, rate, reverse), dst)}")

    pair = "USD per HKD" if reverse else "HKD per USD"
    lines.append(f"rate {rate.hkd_per_usd_fmt} {pair} (source: {rate.source})")
    if rate.as_of:
        lines.append(f"provider timestamp: {rate.as_of}")
    return "\n".join(lines)


def render_json(amounts: Iterable[float], rate: Rate, reverse: bool) -> str:
    payload = {
        "rate": rate.hkd_per_usd,
        "rate_quote": "USD per HKD" if reverse else "HKD per USD",
        "source": rate.source,
        "as_of": rate.as_of,
        "direction": "USD->HKD" if reverse else "HKD->USD",
        "results": [
            {"input": amount, "output": convert(amount, rate, reverse)} for amount in amounts
        ],
    }
    return json.dumps(payload, indent=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hkd2usd",
        description="Convert Hong Kong dollars to US dollars (and back with --reverse).",
        epilog="Rate priority: --rate, then --live, then the built-in 7.80 peg midpoint.",
    )
    parser.add_argument(
        "amounts",
        nargs="*",
        type=parse_amount,
        metavar="AMOUNT",
        help="amounts to convert, e.g. 1000 or '1,500.50' (omit to read stdin)",
    )
    parser.add_argument("--rate", type=float, help="use this rate, HKD per USD")
    parser.add_argument("--live", action="store_true", help="fetch the current market rate")
    parser.add_argument("--timeout", type=float, default=5.0, help="live request timeout in seconds")
    parser.add_argument("--reverse", action="store_true", help="convert USD to HKD instead")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.rate is not None and args.rate <= 0:
        build_parser().error("--rate must be greater than zero")

    rate, warnings = resolve_rate(args)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    amounts = collect_amounts(args.amounts)
    renderer = render_json if args.json else render_text
    print(renderer(amounts, rate, args.reverse))
    return 0


if __name__ == "__main__":
    sys.exit(main())
