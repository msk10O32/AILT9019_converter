# hkd2usd

A small Hong Kong dollar to US dollar converter with three front ends over one
shared conversion core: a standalone web page, a Django page, and a command-line
tool.

- `hkd2usd.html` — a single self-contained page. Open it in a browser and it
  works: no server, no install, no dependencies.
- `hkd2usd.py` — the conversion, parsing, and rate-resolution logic (no
  dependencies, standard library only). The command line and the Django page
  import it, so they cannot disagree about what a valid amount is or which rate
  wins.
- `core/` — the Django app: form, view, templates, stylesheet and script.
- `config/` — Django project settings and root URL configuration.

## Standalone page

Open `hkd2usd.html` in a browser — double-click it, or drag it into a window. It
is one file with its styles and script inline, so there is nothing else to ship
alongside it.

It has the same three rate sources, both directions, the same amount tolerance
(`1000`, `1,500.50`, `HK$1500.50`) and the same validation messages as the other
front ends, and flipping the direction reconverts without a second press. It has
no history table: that lives in the Django page, which is the only front end with
a session to keep it in.

The live rate is fetched by the browser, so it needs an internet connection. The
provider replies with `Access-Control-Allow-Origin: *`, so this works opened
straight from disk as well as from a server. If the request is blocked or the
machine is offline, the page says so and falls back to the peg default rather
than failing.

Its JavaScript is a second copy of the conversion rules, because a single file
cannot import the Python core. `hkd2usd.py` stays the reference implementation:
the page mirrors its amount tolerance, its rate priority and its 7.80 default,
and `test_standalone_page.py` asserts the two still agree on the constants most
likely to drift, plus that the file has not quietly grown an external
dependency.

## Django web interface

```bash
python -m pip install -r requirements.txt
python manage.py migrate          # creates db.sqlite3 for sessions
python manage.py runserver
```

Then open <http://127.0.0.1:8000/>. Enter an amount, pick a direction and a rate
source, and press Convert. The result shows the converted figure, the rate, and
which source it came from; the last 10 conversions are kept in the session and
listed below, with a Clear button.

Pressing either Direction button converts straight away, so seeing the other
direction of the same amount does not need a second press of Convert. The amount
is carried over, and the buttons keep working for as many flips as you like. If
the amount is empty there is nothing to convert, so the press does not submit
and you do not get an error you did not ask for. On a short window the result is
scrolled into view just enough to be visible; when it is already on screen
nothing moves, so the buttons stay where you left them.

The page works without JavaScript. JS drives the direction buttons and shows the
custom-rate field only when it is relevant, keeping it from being submitted
otherwise; the server enforces the same custom-rate rule either way.

## Command line

```bash
python hkd2usd.py 1000              # 1000 HKD -> USD at the 7.80 peg midpoint
python hkd2usd.py 1000 2500 --live  # current market rate
python hkd2usd.py --rate 7.85 1500  # your own rate
python hkd2usd.py 100 --reverse     # USD -> HKD instead
python hkd2usd.py 780 --json        # machine-readable output
printf '50\n125.5\n' | python hkd2usd.py   # batch from stdin
```

| Flag | Meaning |
| --- | --- |
| `--rate R` | Use rate `R`, quoted as HKD per USD |
| `--live` | Fetch the current rate from open.er-api.com |
| `--timeout S` | Live request timeout in seconds (default 5) |
| `--reverse` | Convert USD to HKD instead |
| `--json` | Emit JSON instead of text |

Amounts may be written as `1000`, `1,500.50`, or `HK$1500.50`. Negative amounts
are rejected.

## Where the rate comes from

Every front end resolves the rate the same way, in priority order: an explicit
rate, then the live rate, then the built-in 7.80 default. If the live fetch
fails, the app warns and falls back to the default rather than giving up, so it
still works offline; the reported source always says which one was actually used.

The default is the midpoint of the HKD peg band (7.75–7.85), a reasonable
stand-in for the real rate but not a substitute for one when the exact figure
matters. The live provider is a free, keyless service and is not a trading-grade
feed — don't use this for accounting.

## Tests

```bash
python manage.py test                              # all 57 tests
python -m unittest discover -p "test_*.py"         # the 33 that need no Django
```

Plain `python -m unittest` does not work here: discovery pulls in `core/tests.py`,
which needs Django settings, and fails with `ImproperlyConfigured`. The pattern
above matches only the two Django-free files.

The Django tests cover amount validation, all three rate sources, the
live-fetch fallback, both directions, the custom-rate rules, and the session
history including its cap and the Clear action. The live-fetch failure paths
(unreachable provider, error payload, missing rate, implausible rate) are tested
with the network mocked out, so the suite never depends on the provider being up.

`test_standalone_page.py` checks that `hkd2usd.html` stays one file with no
external script or stylesheet, and that its JavaScript constants match
`hkd2usd.py` rather than having drifted.

The direction buttons and the scroll are client-side, so no server test can
exercise them directly. A small FrontEndContractTests class guards the DOM the
script depends on — the amount input's id, the direction input's name, the
custom-rate hooks — because renaming any of those breaks the behaviour silently
and nothing else would fail. The behaviour itself was verified by driving both
pages in a browser.

## Notes

- `DEBUG = True` and localhost-only `ALLOWED_HOSTS` — this is a local MVP, not a
  deployment configuration. Set `DJANGO_SECRET_KEY` in the environment to
  override the development key.
- Session history lives in the session, not the database, so there are no models
  and nothing to migrate beyond Django's own tables.
