# Calculation methods and conventions

Every number comes from the Swiss Ephemeris (`pyswisseph` 2.10.3.2, SE 2.10.03), applied to the bundled
JPL DE441-based data files. No language model touches any calculation, and nothing is interpolated or estimated
outside the library. Identical input on identical pinned versions gives byte-identical output (`tests/test_behaviour.py::test_deterministic`).

## Frame
- Geocentric, apparent positions (light-time, aberration and nutation applied), ecliptic and equinox of date. This is the standard convention in Western natal astrology software.
- Time scale: civil UTC is treated as UT1 (`swe.calc_ut`). The difference is under 0.9 s, which moves the Moon by less than 0.5″. ΔT (TT−UT) comes from the Swiss Ephemeris model and is reported in every response.
- Longitudes are reported to 1e-7°. Display strings **truncate** degrees, minutes and seconds instead of rounding them (13°25′59.9″ shows as 13°25′), so a point is never pushed over a sign boundary by display rounding.

## Points
| Point | Source | Notes |
|---|---|---|
| Sun … Pluto | `SE_SUN` … `SE_PLUTO` | |
| Chiron | `SE_CHIRON` (`seas_*.se1`) | Asteroid file is required. A missing file returns `MISSING_EPHEMERIS` |
| North Node | **True** (`SE_TRUE_NODE`, osculating) by default; `node: "mean"` gives `SE_MEAN_NODE` | Both are always returned under `variants.north_node` |
| South Node | North Node + 180° | Same variant as the North Node |
| Lilith | **Mean** Black Moon (`SE_MEAN_APOG`) by default; `osculating` = "true" Lilith (`SE_OSCU_APOG`); `interpolated` = `SE_INTP_APOG`, a smoothed apogee without the osculating oscillation | All three are always returned under `variants.lilith` |
| ASC, MC | `swe_houses_ex2` | |
| DSC, IC | ASC + 180°, MC + 180° | |
| Vertex | `ascmc[3]` from `swe_houses_ex2` | Western intersection of the ecliptic with the prime vertical |
| Part of Fortune | see below | |

**Node variants.** The mean node is a smooth average and is always retrograde (about −0.053°/day). The true node includes the Sun's perturbations, wobbles by up to ±1.5° around the mean, and is sometimes briefly direct. Programs differ on which one they show by default, so match the setting when you compare against another program.

**Lilith variants.** Mean Lilith is the averaged lunar apogee (about +0.111°/day). Osculating Lilith is the apogee of the instantaneous Keplerian orbit, can sit up to about 30° from the mean, and can be retrograde. Interpolated Lilith (Swiss Ephemeris "intp. Apogee") removes the spurious osculating oscillation.

## Part of Fortune
- **Day chart:** Fortune = ASC + Moon − Sun.
- **Night chart:** Fortune = ASC + Sun − Moon.
- Day or night (sect): the chart is diurnal when the Sun's ecliptic longitude lies in the half running from the DSC through the MC to the ASC, i.e. `(Sun − ASC) mod 360 ≥ 180°` (houses 7–12). The Sun's true altitude is reported as `houses.sun_altitude_deg`. If the two criteria disagree (the Sun is a fraction of a degree from the horizon and has ecliptic latitude), the engine adds a warning.
- `settings.fortune = "day"` forces the day formula for every chart (some modern programs do this).

## Motion
- `retrograde` ⇔ longitude speed < 0 (deg/day from the Swiss Ephemeris, not a finite difference).
- **Stationary threshold (explicit):** a body is stationary when `|speed| < threshold`. The default thresholds, chosen to be about one day of speed change around a typical station, are:

| Body | Mercury | Venus | Mars | Jupiter | Saturn | Uranus | Neptune | Pluto | Chiron |
|---|---|---|---|---|---|---|---|---|---|
| °/day | 0.10 | 0.03 | 0.012 | 0.002 | 0.001 | 0.0005 | 0.0003 | 0.0003 | 0.0008 |

  Stationary bodies are labelled `stationary_retrograde` (SR) or `stationary_direct` (SD) by the sign of the speed. You can override any threshold with `settings.stationary_thresholds`. The Sun and Moon are never retrograde. Nodes and Lilith report R/D only, without a stationary test.

## Houses
- Default **Placidus**. Also available: **Whole Sign**, **Equal** (cusp 1 = ASC, +30° each), Koch, Porphyry, Regiomontanus and Campanus.
- Whole Sign: house 1 is the whole sign containing the ASC. MC/IC are still reported but are not house cusps.
- House placement uses the half-open interval [cusp n, cusp n+1). A point exactly on a cusp belongs to the house that cusp opens.
- **Polar failure:** Placidus and Koch are undefined when |latitude| > 90° − true obliquity (about 66.56°). The engine raises `HOUSE_SYSTEM_FAILED` with the limit and the fallback options. It never switches system silently, although the Swiss Ephemeris C library does fall back to Porphyry on its own. With `settings.polar_fallback = porphyry | whole_sign | equal` the engine uses that system and records a warning.

## Zodiac
- Default tropical. Sidereal requires an explicit `ayanamsa` (`AYANAMSA_REQUIRED` otherwise). Options: lahiri, fagan_bradley, raman, krishnamurti, yukteshwar, true_chitra, true_revati, true_pushya, deluce, djwhal_khul, sassanian, galactic_center_0sag, j2000.
- In sidereal mode, planets **and** house cusps are sidereal (`SEFLG_SIDEREAL` passed to both). `ayanamsa.value` is the true ayanamsa (includes nutation), which is the amount actually subtracted and the value swetest prints. `ayanamsa.mean_value` excludes nutation.

## Aspects
- Conjunction 0°, sextile 60°, square 90°, trine 120°, opposition 180°.
- Separation = shortest arc. Actual orb = |separation − aspect angle|. The aspect is reported when orb ≤ the limit for that aspect.
- Default orbs: ☌ 8°, ☍ 8°, □ 7°, △ 7°, ⚹ 5°, configurable per aspect (`settings.orbs`, 0–30°). These defaults are this project's own choice, not a copy of any site's defaults. Set them to match the reference you compare against.
- Default points: Sun–Pluto, Chiron, North Node, Lilith, ASC, MC (`settings.aspect_points`, which can also include south_node, dsc, ic, vertex, fortune). Frame pairs are never reported: ASC–DSC, MC–IC, ASC–MC (and DSC/IC combinations), NN–SN.
- **Applying/separating** comes from instantaneous speeds. With `d = signed arc b − a` and `rate = sign(sep − angle) · sign(d) · (v_b − v_a)`, the aspect is `applying` if rate < 0 (orb shrinking) and `separating` if rate > 0. `exact` means orb < 1e-6°. `stationary` means |rate| < 1e-7°/day. Angles use their true speeds from `swe_houses_ex2` (the ASC moves at roughly 360–600°/day), so aspects to angles also get a status. The rate is returned as `orb_rate_deg_per_day`.

## Unknown birth time
- Positions are computed for **12:00 local time**. ASC, MC, DSC, IC, Vertex, Part of Fortune, house cusps and house placements are **omitted**.
- The whole local civil day (00:00:00 to 23:59:59, with DST edges resolved to cover the full day) is sampled 25 times, hourly:
  - `uncertainty.points[id]`: the start and end position, span and signs touched. A point is flagged uncertain if it changes sign during the day. The Moon is always flagged (it moves about 12–15° a day).
  - Aspects are listed if they occur at any sample. `occurs = all_day | part_of_day`, `orb_range` gives the min and max over the day, and `status` is the noon value (null if the aspect isn't in orb at noon). At a 5° orb the Moon spends at least 10 h inside the window, so hourly sampling cannot miss one.

## Time conversion
1. The local civil date/time is read in the requested calendar (Gregorian default, or Julian). Julian dates are converted to the Gregorian equivalent through `swe.julday/revjul`. Gregorian dates before 1582-10-15 trigger a warning.
2. The IANA zone (from GeoNames, timezonefinder, or a manual value) is applied with Python `zoneinfo`, **pinned to the `tzdata` wheel** (`zoneinfo.reset_tzpath([])`), so the host OS's tz files are never used. The tzdb version is reported (currently 2026d).
3. Both `fold` values are evaluated:
   - The two offsets differ and both round-trip, so the time is **ambiguous** (clocks set back): `AMBIGUOUS_LOCAL_TIME` with both candidate UTC instants, unless `ambiguous_time = earlier | later`.
   - Neither round-trips, so the time is **nonexistent** (clocks set forward): `NONEXISTENT_LOCAL_TIME`, unless `nonexistent_time = shift_forward` (read with the pre-change offset) or `shift_backward` (post-change offset).
4. **LMT:** where tzdb has no standard time yet (abbreviation `LMT`), the default is the birthplace's own local mean time, `longitude × 4 min`. tzdb's LMT belongs to the zone's reference city, not the birthplace. `lmt = "zone"` uses tzdb's value instead.
5. `utc_offset` (e.g. `+03:00`) bypasses all zone rules. Use it when you have a documented historical offset (war time, local practice) that differs from tzdb.
6. Before 1970, tzdb coverage is best-effort, and the engine warns about it.

## Supported range
Gregorian years **1200–2999**, using the bundled `sepl/semo/seas` files `_12`, `_18` and `_24` (5.9 MB). Dates outside that range return `UNSUPPORTED_DATE`. Inside it, any file that turns out to be missing returns `MISSING_EPHEMERIS`. The engine checks the return flag of every `calc_ut` call and refuses the Swiss Ephemeris' silent fallback to the lower-precision Moshier model. To extend the range, add the matching `.se1` files from <https://github.com/aloistr/swisseph/tree/master/ephe> and edit `SUPPORTED_YEARS`.


## Interpretation (`astrocalc/interpret.py`)

1. **Facts** (deterministic): sign, house, retrograde for Sun–Pluto, Chiron, North Node, Lilith, ASC, MC and Fortune;
   element/modality balance (Sun, Moon and ASC count 2, Mercury–Saturn count 1, Uranus–Pluto count 0.5); chart ruler
   (modern rulers: Scorpio = Pluto, Aquarius = Uranus, Pisces = Neptune); sign clusters (3+ of Sun–Pluto in a sign);
   house clusters (3+ in a house); planets in angular houses; the 8 tightest aspects among the main points, with
   personal-planet aspects first. For unknown birth times, house and angle facts are omitted, and fast points that
   change sign during the day are listed with both possible signs.
2. **Template reading**: built from the fixed vocabulary in `meanings.py`, which is always available.
3. **AI writer** (optional): the system prompt is in `interpret.SYSTEM_PROMPT`. Temperature is 0.4 and the output
   is JSON. **Claim checker** (`validate_claims`): rejects any sign or house statement that disagrees with the chart,
   any degree figure other than a real aspect orb, and any house, Ascendant or Midheaven mention when the birth time
   is unknown. One retry is made with the corrections; after that the template is used.

## Ideal match (`astrocalc/match.py`)

- Candidates: every day from (birth year − N) Jan 1 to min(birth year + N Dec 31, today), computed at 12:00 UT
  with the same zodiac and ayanamsa. Points used are Sun, Moon, Mercury, Venus, Mars, Jupiter and Saturn.
- User points: Sun, Mercury, Venus, Mars, Jupiter, Saturn, plus the Moon (dropped if the time is unknown and the
  day's Moon span is over 14°), plus the ASC when the birth time is known.
- Contact score = pair weight × aspect quality × (1 − orb / max orb). Max orb is 6° for contacts involving
  Sun, Moon or ASC and 4° otherwise. The partner's Moon gets an extra 6.5° of orb and is weighted × 0.6.

| Pair | Weight | | Pair | Weight |
|---|---|---|---|---|
| Sun–Moon | 10 | | Sun/Moon/Venus–ASC | 6 |
| Venus–Mars | 9 | | Mars–ASC, Sun–Mars, Moon–Mars, Mercury–Mercury | 4 |
| Moon–Moon, Sun–Venus, Moon–Venus | 7 | | Jupiter–Sun/Moon/Venus | 4 |
| Venus–Venus | 6 | | Saturn–Sun/Moon/Venus, Mars–Mars, Mercury–Sun/Moon/Venus | 3 |
| Sun–Sun | 5 | | | |

  Aspect quality: trine +1.0, sextile +0.7, conjunction +1.0 (+0.3 for Saturn or Mars–Mars), opposition +0.4
  (−0.6 with Saturn), square −0.6 (−1.0 with Saturn).
- **Windows**: runs of days in the top 10% by slow-planet score (all planets except the Moon), with gaps of ≤2
  days merged. Ranked by peak score, with at most 2 windows per Sun sign. The "best dates" are the 3 days in a
  window with the highest total score including the Moon.
- **Match strength** = window peak ÷ best day in the scan × 100. **Sun-sign ranking** = average slow score of all
  scanned days with that Sun sign, rescaled 0–100.
- These weights are a conventional synastry heuristic. They are not empirically validated, and the UI shows a
  disclaimer.
