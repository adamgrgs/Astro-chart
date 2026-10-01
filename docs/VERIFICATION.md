# Verification

Run `pytest -q`: 44 tests pass. Without the optional JPL file, 37 pass and 7 are skipped. Three independent kinds of evidence back the results.

## 1. Swiss Ephemeris reference program, matching settings (strong)

`scripts/fetch_reference.py` queries Astrodienst's public **swetest** service (<https://www.astro.com/cgi/swetest.cgi>).
swetest is the Swiss Ephemeris authors' own reference program, run on their servers. The script queries 12 cases
and stores the raw output in `tests/fixtures/swetest_reference.json`. The cases cover:
Cairo 1987 with Placidus, Whole Sign + Lahiri, Equal, and Placidus + Fagan/Bradley; New York 1990; Sydney 1975 (southern
hemisphere); Reykjavík 2000 (64°N); Tromsø 1995 with Porphyry (69.6°N); London 1850; Tokyo 2150 with Koch; Paris 1650 with
Regiomontanus (`_12` file); and Rio 2500 with Campanus (`_24` file).

Every case is compared for Sun–Pluto, Chiron, true and mean node, mean/osculating/interpolated Lilith, ASC, MC, Vertex,
all 12 cusps, speeds, and the sidereal ayanamsa. The tolerance is 0.1″, and the **maximum observed deviation is 0.00000″**.
This confirms the flags, frame, house codes and ayanamsa handling are identical to the reference program.

## 2. Independent ephemeris, different code base (strong)

`tests/test_independent_skyfield.py` compares Sun–Pluto against NASA JPL **DE421** through Skyfield, which is
independent of Swiss Ephemeris code. The comparison uses 6 moments between 1947 and 2033. Maximum |difference| in apparent ecliptic longitude of date:
Sun 0.04″, Moon 0.57″, Mercury 0.04″, Venus 0.002″, Mars 0.02″, Jupiter 0.01″, Saturn 0.001″, Uranus 0.14″,
Neptune 0.07″, Pluto 0.08″. The remaining differences come from ΔT and nutation models and from the DE421 vs DE441 ephemerides.
All of them are far below the 1′ display resolution.

## 3. Required test case: 7 July 1987, 00:30, Cairo, Egypt, 30°04′N 31°15′E

**Historical UTC offset: UTC+3 (EEST, Egyptian summer time) → 1987-07-06 21:30:00 UTC.**
- IANA tzdb `africa` file: `Rule Egypt 1984 1988 - May 1 1:00 1:00 S` and `Rule Egypt 1966 1994 - Oct 1 3:00 0 -`, i.e. DST from 1 May 01:00 to 1 Oct 03:00 in 1987, with zone `Africa/Cairo 2:00 Egypt EE%sT`.
- Corroborated by timeanddate.com's Cairo 1987 page: "Start DST: Friday, May 1, 1987, 1:00 am clocks turned forward 1 hour … End DST: Thursday, October 1, 1987, 3:00 am clocks turned backward." timeanddate keeps its own database, so this is a second source but not a fully independent archival one.
- The tests also check the edges: 1987-05-01 01:30 is rejected as nonexistent, and 1987-10-01 02:30 is rejected as ambiguous (UTC 23:30 on Sep 30 or 00:30 on Oct 1).

Tropical, Placidus, true node, mean Lilith (engine vs swetest):

| Point | Engine | swetest | Δ | House | Motion |
|---|---|---|---|---|---|
| Sun | 14°16′45.98″ Can | 14°16′45.98″ Can | 0.0000″ | 4 | direct |
| Moon | 15°32′09.81″ Sco | 15°32′09.81″ Sco | 0.0000″ | 7 | direct |
| Mercury | 10°04′19.30″ Can | 10°04′19.30″ Can | 0.0000″ | 4 | retrograde |
| Venus | 1°18′28.30″ Can | 1°18′28.30″ Can | 0.0000″ | 3 | direct |
| Mars | 0°07′32.70″ Leo | 0°07′32.70″ Leo | 0.0000″ | 4 | direct |
| Jupiter | 26°44′04.48″ Ari | 26°44′04.48″ Ari | 0.0000″ | 1 | direct |
| Saturn | 15°56′56.60″ Sag | 15°56′56.60″ Sag | 0.0000″ | 9 | retrograde |
| Uranus | 23°55′12.51″ Sag | 23°55′12.51″ Sag | 0.0000″ | 9 | retrograde |
| Neptune | 6°24′25.85″ Cap | 6°24′25.85″ Cap | 0.0000″ | 9 | retrograde |
| Pluto | 7°11′04.51″ Sco | 7°11′04.51″ Sco | 0.0000″ | 7 | retrograde |
| Chiron | 24°10′00.98″ Gem | 24°10′00.98″ Gem | 0.0000″ | 3 | direct |
| North Node (true) | 6°16′51.18″ Ari | 6°16′51.18″ Ari | 0.0000″ | 12 | retrograde |
| South Node | 6°16′51.18″ Lib | (NN + 180°) | 0.0000″ | 6 | retrograde |
| Lilith (mean) | 25°14′38.01″ Can | 25°14′38.01″ Can | 0.0000″ | 4 | direct |
| Ascendant | 11°42′26.06″ Ari | 11°42′26.06″ Ari | 0.0000″ | 1 | |
| Midheaven | 7°25′05.16″ Cap | 7°25′05.16″ Cap | 0.0000″ | 10 | |
| Descendant | 11°42′26.06″ Lib | (ASC + 180°) | 0.0000″ | 7 | |
| IC | 7°25′05.16″ Can | (MC + 180°) | 0.0000″ | 4 | |
| Vertex | 5°01′56.66″ Lib | 5°01′56.66″ Lib | 0.0000″ | 6 | |
| Part of Fortune (night) | 10°27′02.23″ Sag | ASC + Sun − Moon from swetest values = 250.4506° | 0.0000″ | 8 | |

Mean node: 6°35′53.53″ Ari. Osculating Lilith: 2°06′19.28″ Leo. Interpolated Lilith: 27°05′59.73″ Can.

House cusps (Placidus): 1 11°42′ Ari · 2 17°20′ Tau · 3 14°03′ Gem · 4 7°25′ Can · 5 1°49′ Leo · 6 1°50′ Vir ·
7 11°42′ Lib · 8 17°20′ Sco · 9 14°03′ Sag · 10 7°25′ Cap · 11 1°49′ Aqu · 12 1°50′ Pis. All match swetest exactly.

It is a night chart because the Sun is in house 4 (altitude −36.8°), so Fortune uses ASC + Sun − Moon.

### Not verified
- **Astro-Seek** itself could not be queried automatically, because Cloudflare blocks scripted access (HTTP 403). To compare by hand, enter the Cairo case on Astro-Seek with Placidus, true node and mean Lilith. You should see the minute values above. Aspect lists will differ unless you set the orbs to match.

## 4. Behaviour tests (`tests/test_behaviour.py`, `tests/test_api.py`)
Covered: the Cairo offset (summer +3 and winter +2), the New York 2021 DST gap and overlap, birthplace vs zone LMT (London 1840),
manual offset, timezone and coordinate overrides, Julian-calendar equivalence, unsupported years, malformed input, a
removed ephemeris directory (gives `MISSING_EPHEMERIS`, never Moshier), Placidus failure at Tromsø plus the fallback,
the explicit sidereal ayanamsa requirement and its consistency, Whole Sign and Equal cusps, unknown time (no angles, Moon
flagged, Sun sign change on 1990-12-21 flagged), the Mercury station of 2023-04-21 being reported as stationary, the
applying/separating sign, orb limits, the Fortune day, night and forced-day formulas, truncation, determinism, the
summary text, and the API error shape.
