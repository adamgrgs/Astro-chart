# Natal Chart Calculator

A web-based natal astrology calculator with roughly the calculation scope of Astro-Seek's birth-chart page. Every
position comes from the **Swiss Ephemeris**. Local birth times are converted to UTC with **IANA tzdb** historical
rules, and birthplaces are resolved with **GeoNames**. No language model or estimate is involved anywhere in the
calculation path.

- **Points:** Sun, Moon, Mercury–Pluto, Chiron, North/South Node (true or mean), Black Moon Lilith (mean, osculating or interpolated), ASC, MC, DSC, IC, Vertex, Part of Fortune (day/night), and 12 house cusps.
- **For each point:** sign, degree/minute/second, house, speed, declination, and direct / retrograde / stationary status (explicit thresholds).
- **Aspects:** ☌ ☍ □ △ ⚹ with actual orb, configurable orb limits, and applying/separating status.
- **Zodiac and houses:** tropical (default) or sidereal with an explicit ayanamsa. Placidus (default), Whole Sign, Equal, Koch, Porphyry, Regiomontanus, Campanus.
- **Explicit failures:** ambiguous and nonexistent local times, unsupported dates, missing ephemeris files, polar house-system failures, unknown places and timezones.
- **Unknown birth time:** houses and angles are omitted, and day-wide ranges flag uncertain placements and aspects.
- **Output:** a complete JSON response plus copyable plain-text summaries (placements, houses, aspects, full).

Methods and conventions are in [`docs/METHODS.md`](docs/METHODS.md), the HTTP API in [`docs/API.md`](docs/API.md),
and the verification evidence in [`docs/VERIFICATION.md`](docs/VERIFICATION.md).

## Architecture

```
web/index.html      static UI (vanilla JS, served by the API at /)
api/index.py        FastAPI app: POST /api/chart, /api/interpret, /api/match; GET /api/places, /api/timezone, /api/meta, /api/health, /docs
astrocalc/
  timeconv.py       local -> UTC (zoneinfo pinned to the tzdata wheel; ambiguity/gap/LMT policies)
  geo.py            GeoNames API (if GEONAMES_USERNAME) or bundled GeoNames cities5000 index + timezonefinder
  engine.py         Swiss Ephemeris calls, houses, angles, Fortune, motion; refuses Moshier fallback
  aspects.py        aspects, orbs, applying/separating
  chart.py          request orchestration, unknown-time analysis, summaries
  interpret.py      chart facts -> plain-English reading (template, or AI writer + claim checker)
  match.py          ideal-match finder: deterministic synastry scan over partner birth dates
  meanings.py       fixed plain-English vocabulary for signs, planets, houses, aspects
  llm.py            optional server-side AI call (Anthropic or OpenAI), stdlib HTTP only
ephe/               Swiss Ephemeris data files (sepl/semo/seas _12 _18 _24 -> years 1200-2999, 5.9 MB)
data/places.tsv.gz  GeoNames cities5000 extract (69,762 places with IANA tz ids, 3.8 MB)
tests/              swetest reference cases, JPL DE421 cross-check, tz/edge-case tests, API tests
```

The Swiss Ephemeris keeps its state in thread-local storage. The engine therefore sets the ephemeris path in
every worker thread and serialises calls behind a lock, so one request's sidereal mode can never leak into another.

## Run locally

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt          # pyswisseph builds from source: needs a C compiler
uvicorn api.index:app --reload --port 8000   # UI at http://localhost:8000, OpenAPI at /docs
pytest -q                                    # 53 tests
DE421_PATH=/path/to/de421.bsp pytest -q tests/test_independent_skyfield.py   # optional JPL cross-check
```

## Interpretation and ideal match

- **Positions are never produced by AI.** `/api/interpret` and `/api/match` recompute the chart server-side from the
  birth data, build a facts object (Big Three, element balance, chart ruler, clusters, tightest aspects), and only then
  ask the AI to write prose about those facts.
- **Claim checker.** Every "<Planet> in <Sign>", "<Sign> <Planet>", "<Planet> in the Nth house" and any degree figure
  in the AI text is compared with the calculation (for unknown birth times, houses/rising are forbidden). One
  corrective retry; if it still disagrees, the AI text is discarded and the deterministic template reading is shown.
  The response says which source was used (`reading.source` = `ai` or `template`).
- **Ideal match.** `match.py` scans every partner birth date in a ±N-year window (never after today) at 12:00 UT and
  scores synastry contacts (Sun–Moon, Venus–Mars, Moon–Moon, Sun–Venus …). It returns the best birth-date windows,
  their Sun/Venus/Mars signs, reasons and cautions, and a 12-sign ranking. Full method in `docs/METHODS.md`.
  The partner's Moon depends on their unknown birth time and is flagged as such.
- **Without an AI key** both features still work using the template text.

## Deploy

**Vercel (current target).** The repo is ready for zero-config Python deployment: `vercel.json` routes every path
to `api/index.py` and bundles `astrocalc/`, `ephe/`, `data/` and `web/` into the function.
1. Import `adamgrgs/Astro-chart` into Vercel (framework preset "Other"). The build runs `pip install -r requirements.txt`.
2. Optional: add `GEONAMES_USERNAME` as an environment variable (Production and Preview). Without it, place search uses the bundled offline index.
3. Optional: add `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) to enable AI-written readings. Optional `ANTHROPIC_MODEL`,
   `OPENAI_MODEL`, `AI_TIMEOUT_SECONDS`, `AI_RATE_PER_10_MIN` (default 12 AI calls per IP per 10 min per instance).
4. If the team's Deployment Protection covers the URL you want public, turn it off for this project or attach a custom domain.

**Anywhere else.** `docker build -t natal . && docker run -p 8000:8000 -e GEONAMES_USERNAME=… natal`.

**Constraints**
- `pyswisseph` ships no Linux wheels, so it compiles from source. The build environment needs gcc (Vercel's build image and the Dockerfile both provide it).
- The function bundle is about 120 MB unzipped: app data is 10 MB, and numpy, timezonefinder-data and pydantic make up the rest. That is under Vercel's 250 MB limit. Measured locally: the place index loads lazily on the first search (about 1.4 s), a chart takes about 2 ms, an unknown-time chart about 11 ms, and an offline place search about 45 ms.
- Fully stateless: no database and no writes. Responses are deterministic for pinned versions.

## Accounts, credentials, files, licensing, costs

| Item | Needed? | Where | Cost / limits | Notes |
|---|---|---|---|---|
| Swiss Ephemeris library (`pyswisseph`) | yes | PyPI | free under **AGPL-3.0**, or the Swiss Ephemeris Professional License at **CHF 700** one-time (unlimited) [astro.com price list, 2026-10-01] | Under AGPL a public web service must offer its complete source to users. This repo is public and AGPL-licensed, and the UI links to it. Buy the professional license only if the code ever goes closed-source |
| Ephemeris data files `sepl/semo/seas_*.se1` | yes (bundled) | <https://github.com/aloistr/swisseph/tree/master/ephe> | free (same license) | `_12/_18/_24` cover 1200–2999 (DE441-based). Without `seas_*`, Chiron fails explicitly |
| GeoNames account (`GEONAMES_USERNAME`) | optional | <https://www.geonames.org/login>, then enable "Free Web Services" on the account page | free: 10,000 credits/day, 1,000/hour [geonames.org/export, 2026-10-01]. Premium plans exist for higher volume | Server-side env var only, never sent to the browser. Without it, the offline index of all places with population ≥ 5,000 plus `timezonefinder` is used |
| GeoNames data dump (offline index) | bundled | download.geonames.org | free, **CC BY 4.0** (attribution in the UI footer) | Rebuild with `python scripts/build_places.py` |
| IANA tzdb | bundled via `tzdata` wheel | PyPI | free, public domain | Pinned at 2026d. Bump `tzdata` deliberately and re-run the tests |
| timezonefinder | bundled | PyPI | free, MIT | Offline coordinate → IANA zone |
| Anthropic API key (`ANTHROPIC_API_KEY`) | optional | console.anthropic.com → API keys | pay per use: one reading or match profile is roughly 3k input + 2k output tokens (a few US cents with a Sonnet-class model; check current pricing) | Server-side env var only. `OPENAI_API_KEY` works as an alternative. Without a key, template text is used |
| Hosting | yes | Vercel (Pro team already exists) or any Docker host | Vercel function usage is within the existing plan at hobby-level traffic | |

## Licence

AGPL-3.0 (see `LICENSE`), as required by the Swiss Ephemeris free edition. Swiss Ephemeris © Astrodienst AG.
Place data © GeoNames contributors, CC BY 4.0.
