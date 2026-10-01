# HTTP API

Interactive OpenAPI docs are served at `/docs`. All responses are JSON.

## `POST /api/chart`

```json
{
  "date": "1987-07-07",
  "time": "00:30",
  "place": "Cairo, Egypt",
  "latitude": "30°04′N",
  "longitude": "31°15′E",
  "settings": { "house_system": "placidus" }
}
```

| Field | Default | Meaning |
|---|---|---|
| `date` | required | Local civil date `YYYY-MM-DD` |
| `time` | – | Local clock time `HH:MM[:SS]`. Omit it, or send `time_unknown: true`, for an unknown time |
| `calendar` | `gregorian` | `julian` for Old Style records |
| `place` / `geonameid` | – | Place search text, or an exact GeoNames id from `/api/places` |
| `latitude`, `longitude` | from place | **Override.** Decimal or DMS (`30°04′N`, `30N04`, `31 15 E`) |
| `timezone` | from place/coords | **Override.** IANA name |
| `utc_offset` | – | **Override.** Fixed offset such as `+03:00`. Bypasses all tz rules |
| `ambiguous_time` | `reject` | `earlier` / `later` for repeated local times (fall-back hour) |
| `nonexistent_time` | `reject` | `shift_forward` / `shift_backward` for skipped local times (spring-forward hour) |
| `lmt` | `birthplace` | Before standard time: birthplace LMT (longitude × 4 min), or `zone` (tzdb reference-city LMT) |
| `settings.zodiac` | `tropical` | `sidereal` requires `settings.ayanamsa` |
| `settings.house_system` | `placidus` | `whole_sign`, `equal`, `koch`, `porphyry`, `regiomontanus`, `campanus` |
| `settings.polar_fallback` | `none` | `porphyry` / `whole_sign` / `equal`, used only when Placidus/Koch fail |
| `settings.node` | `true` | `mean` |
| `settings.lilith` | `mean` | `osculating`, `interpolated` |
| `settings.fortune` | `sect` | `day` = always ASC + Moon − Sun |
| `settings.orbs` | ☌8 ☍8 □7 △7 ⚹5 | e.g. `{"trine": 6}` |
| `settings.aspect_points` | Sun–Pluto, Chiron, NN, Lilith, ASC, MC | Any point ids |
| `settings.stationary_thresholds` | see METHODS | °/day per body |

Response (abridged):

```json
{
  "time": {"utc": "1987-07-06T21:30:00Z", "utc_offset": "+03:00", "abbreviation": "EEST", "dst": true,
           "source": "iana", "timezone": "Africa/Cairo", "tzdata_version": "2026d", "julian_day_ut": 2446983.39583333},
  "location": {"latitude": 30.0666667, "longitude": 31.25, "timezone": "Africa/Cairo", "...": "..."},
  "points": [{"id": "sun", "longitude": 104.2794388, "sign": "Cancer", "deg": 14, "min": 16, "sec": 45,
              "formatted": "14°16′ Cancer", "house": 4, "speed_deg_per_day": 0.9530639,
              "motion": {"status": "direct", "retrograde": false, "stationary": false}}],
  "houses": {"system": "placidus", "cusps": [{"house": 1, "longitude": 11.7072517, "formatted": "11°42′ Aries"}]},
  "aspects": [{"a": "sun", "b": "moon", "type": "trine", "orb": 1.2558, "orb_formatted": "1°15′", "status": "separating"}],
  "variants": {"north_node": {"true": {}, "mean": {}}, "lilith": {"mean": {}, "osculating": {}, "interpolated": {}}},
  "uncertainty": null,
  "summaries": {"placements": "Sun: 14°16′ Cancer, House 4\n…", "aspects": "…", "houses": "…", "full_text": "…"},
  "engine": {"swisseph_version": "2.10.03", "ephemeris_files_used": [{"file": "sepl_18.se1", "jpl_de": 441}]},
  "warnings": []
}
```

## Errors

Errors come back as HTTP 4xx/5xx with this body: `{"error": {"code", "message", "details"}}`

| Code | HTTP | When |
|---|---|---|
| `INVALID_INPUT` | 422 | Malformed date/time/coords, or an unknown option |
| `UNSUPPORTED_DATE` | 422 | Year outside 1200–2999 |
| `AMBIGUOUS_LOCAL_TIME` | 422 | Repeated local time. `details.options` gives both UTC instants |
| `NONEXISTENT_LOCAL_TIME` | 422 | Skipped local time. `details.options` gives both readings |
| `UNKNOWN_TIMEZONE` | 422 | Bad IANA name, or no zone found for the coordinates |
| `PLACE_NOT_FOUND` | 422 | Place search found nothing and no coordinates were given |
| `AYANAMSA_REQUIRED` | 422 | Sidereal without an ayanamsa |
| `HOUSE_SYSTEM_FAILED` | 422 | Placidus/Koch inside the polar circle. `details.fallback_options` |
| `MISSING_EPHEMERIS` | 500 | A required `.se1` file is absent (the Moshier fallback is refused) |
| `EPHEMERIS_ERROR` | 500 | Any other Swiss Ephemeris error |
| `GEOCODER_UNAVAILABLE` | 503 | GeoNames failed and no offline index is available |

## Other endpoints
- `GET /api/places?q=Cairo&limit=8`: place candidates (`geonameid`, `label`, `lat`, `lon`, `timezone`, `population`, `source`).
- `GET /api/timezone?lat=30N04&lon=31E15`: IANA zone for coordinates.
- `GET /api/meta`: options, defaults, versions, attribution.
- `GET /api/health`: 200 when the ephemeris files are present, otherwise 503.


## POST /api/interpret
Body: the same as `/api/chart`, plus `ai` (bool, default true). Returns `facts`, `reading`
{summary, sections[{title, body}], source: "ai"|"template", provider, model, guardrail, note}, `chart_summary`,
`disclaimer`.

## POST /api/match
Body: the same as `/api/chart`, plus `years_before` (0–40, default 10), `years_after` (0–40, default 10), `top`
(1–12, default 6) and `ai`. Returns:
- `search`
- `windows[]`: from, to, best_dates, peak_date, match_strength, top_percent_of_days, sun_signs, venus_signs,
  mars_signs, mercury_signs, moon_signs_best_dates, reasons, cautions
- `sun_sign_ranking[]`
- `method`
- `profile` (same shape as `reading`)
- `disclaimer`
