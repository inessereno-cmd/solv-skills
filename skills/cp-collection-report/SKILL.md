---
name: clearpay-collection-dashboard
description: Build the partner-facing ClearPay Collection Metrics dashboard (self-contained HTML file) for any Solv partner and date range, using app-faithful semantics from observatory_service.py. Use this skill whenever the user mentions "build the clearpay dashboard for [partner]", "clearpay collection metrics", "observatory dashboard", "rebuild clearpay collections HTML", "partner clearpay collection performance", "ClearPay shown vs collected for [partner]", "[partner] collections dashboard", or any variation of generating a partner-level ClearPay collections report as an HTML artifact. Also trigger when a user asks to refresh/regenerate an existing ClearPay dashboard with a new date range or for a different partner. This skill produces an interactive HTML file with KPIs, a shown-vs-collected waterfall, and a sortable locations table — it is the correct tool for that specific deliverable. Do NOT use for ad-hoc ClearPay queries (use clearpay-analysis), or for generic location-level reporting (use locations-audit-skill).
metadata:
  last_updated: 2026-04-22
  dependencies: group-location-analysis, clearpay-analysis, dbt-sql-analysis
---

# ClearPay Collection Dashboard Builder

Generate an HTML dashboard showing partner-level ClearPay collection metrics (shown vs collected for Copay, Deductible+Coinsurance, Self-Pay, plus Overcollections and No-RTE revenue). Aligned with `observatory_service.py` / `invoice_estimates.py` so the numbers match what partners see in the Observatory product.

## Scope

- **Partner-level summary** of discharged bookings over a date range
- Four KPI cards (Total POS, Copay, Ded+Coins, Self-Pay), waterfall attribution, Additional/Unknown breakdown, sortable locations table
- One self-contained HTML file — no external dependencies besides what's already in `template.html`

## Prerequisites

Always invoke `group-location-analysis` first to resolve the exact `group_id` from a partner name. Never pattern-match on group names in the data queries.

## Workflow

1. **Resolve `group_id`** from the partner name using `group-location-analysis`.
2. **Confirm date range.** If the user said "past week", "last month", etc., compute explicit `start_date` and `end_date` and restate them in the response so they have a chance to correct.
3. **Run the 3 queries below** against `dbt_remote_mcp` — totals, daily, locations. Use the shared base CTE; only the final `group by` differs.
4. **Fill the template** (`template.html` bundled with this skill) by replacing the two placeholder markers:
   - `__DAILY_JSON__` → JSON array of daily rows
   - `__LOCATIONS_JSON__` → JSON array of location rows
   - Also substitute: the filter-bar `Date Range` string, the footer text, the locations "Data through" sub-label, the CSV filename.
5. **Save** to `/mnt/user-data/outputs/ClearPay_Collection_Metrics_<Partner>_Discharged.html` and present via `present_files`.

## Key semantic rules (authoritative source: `clearpay_dashboard_methodology.md`)

Short version. Read the methodology doc if anything below is unclear.

- **Booking universe:** all `b.status = 'discharged'`. Do **not** filter on `cp.has_payment`.
- **Join:** `LEFT JOIN fact_bookings_clearpay_payments` (some discharged bookings have no `cp` row).
- **`actual_billed`** (POS, net of refunds):
  ```
  case when cp.sum_paid_amount_pos > 0
       then greatest(cp.sum_paid_amount_pos - coalesce(cp.sum_refunds, 0), 0)
       else null end
  ```
- **Bucket assignment** — each booking goes to exactly one bucket:
  ```
  case
    when cp.estimate_failed = true or cp.solv_estimate_in_network is null then 'failed_no_estimate'
    when cp.solv_estimate_in_network = 0                                  then 'zero_cost'
    when cp.estimate_type in ('copay','deductible','coinsurance','self_pay','zero_cost')
                                                                           then cp.estimate_type
    else 'other'
  end
  ```
- **Copay / Ded+Coins collected:** capped at full `estimate_total` per booking → `sum(least(coalesce(actual_billed, 0), estimate_total))`.
- **Self-Pay collected:** RAW, NOT capped. Filtered by the broader `is_self_pay` flag:
  ```
  cp.estimate_type = 'self_pay' OR b.insurer_type in ('self-pay', 'selfPay')
  ```
- **Deductible + Coinsurance is combined into one bucket** per the app (`deductible_coinsurance_shown_cents`).
- **Other / Mixed bucket:** bookings with `estimate_type` in `mixed / oop_max_met / fixed_amount / other` (i.e. the `'other'` bucket from the CASE). Aggregated as a capped row (`LEAST(actual_billed, estimate_total)`) for consistency with copay/ded+coins — surfaces ~0.6% of POS that would otherwise be invisible.
- **Spillover** = overcollection above estimate for copay/ded+coins bookings only (does NOT include 'other' or 'zero_cost' overcollection — those are known limitations documented in the methodology).
- **No-estimate collected (insured):** POS dollars collected on bookings where `estimate_total IS NULL` AND `is_self_pay = false`. Self-pay patients are deliberately excluded because RTE doesn't apply to them — those dollars show up in the Self-Pay bucket instead.
- **POS-only scope:** `actual_billed` uses `sum_paid_amount_pos - sum_refunds`, not `sum_paid_amount - sum_refunds`. This matches the dashboard label "Total POS Collected" but diverges from the app's `actual_billed_amount` (which includes post-visit bill payments) for partners with bill activity. For NextCare and most ClearPay partners this is equivalent because `sum_paid_amount_bill` is ~$0. For bill-heavy partners, flag the divergence in the response.

## SQL: shared base CTE

Used by all three queries. Swap `<group_id>`, `<start_date>`, `<end_date>`.

```sql
with base as (
    select
        b.id,
        date(b.local_appointment_date)                                           as appt_date,
        l.state,
        l.display_name_secondary                                                 as clinic_name,
        cp.solv_estimate_in_network                                              as estimate_total,
        cp.estimate_type,
        case
            when cp.sum_paid_amount_pos > 0
                then greatest(cp.sum_paid_amount_pos - coalesce(cp.sum_refunds, 0), 0)
            else null
        end                                                                      as actual_billed,
        case
            when cp.estimate_type = 'self_pay'
              or b.insurer_type in ('self-pay', 'selfPay')
                then true else false
        end                                                                      as is_self_pay,
        case
            when cp.estimate_failed = true or cp.solv_estimate_in_network is null then 'failed_no_estimate'
            when cp.solv_estimate_in_network = 0                                  then 'zero_cost'
            when cp.estimate_type in ('copay','deductible','coinsurance','self_pay','zero_cost')
                                                                                   then cp.estimate_type
            else 'other'
        end                                                                      as bucket
    from {{ ref('dim_bookings') }} b
    inner join {{ ref('dim_locations') }} l on b.location_id = l.id
    left join {{ ref('fact_bookings_clearpay_payments') }} cp on b.id = cp.id
    where b.group_id = <group_id>
      and b.group_id not in (21, 12195)
      and b.status = 'discharged'
      and date(b.local_appointment_date) between '<start_date>' and '<end_date>'
)
```

## SQL: three aggregations (shared SELECT)

The `select` list is identical for all three — only the final `group by` changes.

```sql
    count(*)                                                                                                     as bookings_total,
    sum(case when estimate_total is not null then 1 else 0 end)                                                  as bookings_with_estimate,
    round(sum(coalesce(actual_billed, 0)), 2)                                                                    as total_pos_collected,
    round(sum(case when bucket = 'copay'                          then estimate_total else 0 end), 2)            as copay_shown,
    round(sum(case when bucket = 'copay' and estimate_total is not null
             then least(coalesce(actual_billed, 0), estimate_total) else 0 end), 2)                              as copay_collected,
    round(sum(case when bucket in ('deductible','coinsurance')    then estimate_total else 0 end), 2)            as ded_coins_shown,
    round(sum(case when bucket in ('deductible','coinsurance') and estimate_total is not null
             then least(coalesce(actual_billed, 0), estimate_total) else 0 end), 2)                              as ded_coins_collected,
    round(sum(case when bucket = 'self_pay'                       then estimate_total else 0 end), 2)            as self_pay_shown,
    round(sum(case when actual_billed is not null and is_self_pay = true
             then actual_billed else 0 end), 2)                                                                  as self_pay_collected_raw,
    -- "Other / Mixed" bucket (Issue 3 fix): capped like copay/ded+coins for consistency.
    round(sum(case when bucket = 'other'                          then estimate_total else 0 end), 2)            as other_shown,
    round(sum(case when bucket = 'other' and estimate_total is not null
             then least(coalesce(actual_billed, 0), estimate_total) else 0 end), 2)                              as other_collected,
    round(sum(case when actual_billed is not null and estimate_total is not null
              and bucket in ('copay','deductible','coinsurance')
             then greatest(actual_billed - estimate_total, 0) else 0 end), 2)                                    as overcollection_spillover,
    -- No-RTE bucket (Issue 2 fix): exclude self-pay — RTE doesn't apply to them, and they're already
    -- counted in self_pay_collected_raw. This bucket is "insurance bookings where RTE didn't fire".
    round(sum(case when actual_billed is not null and estimate_total is null
              and is_self_pay = false
             then actual_billed else 0 end), 2)                                                                  as no_estimate_insured_collected
from base
```

- **Totals query:** no `group by` (or `group by ()`). Single row.
- **Daily query:** `group by appt_date order by appt_date`.
- **Locations query:** `group by state, clinic_name order by state, clinic_name`.

## Filling the template

`template.html` contains two placeholder markers that must be replaced verbatim:

| Placeholder | Replace with |
|---|---|
| `__DAILY_JSON__` | `json.dumps(daily_rows)` — array of 14-element rows: `[dt, bookings_total, bookings_with_estimate, total_pos, copay_shown, copay_collected, dc_shown, dc_collected, sp_shown, sp_collected_raw, other_shown, other_collected, spillover, no_estimate_insured]` |
| `__LOCATIONS_JSON__` | `json.dumps(location_rows)` — array of 15-element rows: `[state, clinic_name, bookings_total, bookings_with_estimate, total_pos, copay_shown, copay_collected, dc_shown, dc_collected, sp_shown, sp_collected_raw, other_shown, other_collected, spillover, no_estimate_insured]` |

**Column order matters.** `other_shown` and `other_collected` sit between `sp_collected_raw` and `spillover`. `no_estimate_insured` is the last column. If you reorder them the waterfall and locations table will render wrong values.

Also update these string literals in the HTML (find-and-replace):

| Find | Replace with |
|---|---|
| `<!-- PARTNER_NAME -->` | e.g., `NextCare` (appears 3× — header subtitle, filter bar, footer) |
| `<!-- DATE_RANGE -->` | e.g., `Mar 19 – Apr 17, 2026` (2× — filter bar, footer) |
| `<!-- END_DATE -->` | e.g., `2026-04-17` (1× — locations card "Data through" sub-label) |
| `<!-- CSV_FILENAME -->` | e.g., `clearpay-nextcare-2026-03-19-to-2026-04-17.csv` (1× — CSV download filename) |
| `<!-- GENERATED_DATE -->` | today's date, e.g., `2026-04-22` (1× — footer) |

## Output conventions

- **Filename:** `ClearPay_Collection_Metrics_<PartnerNoSpaces>_Discharged.html` in `/mnt/user-data/outputs/`.
- **Partner slug:** `NextCare` → `NextCare`; `Hometown Urgent Care` → `Hometown_Urgent_Care` (underscores for spaces, keep the case).
- **Present** via `present_files` with a succinct summary of the top-level totals (discharged count, Total POS, Copay %, Ded+Coins %, Self-Pay %).
- **Do not narrate** the template filling or SQL execution in the final message — just the numbers and the file link.

## Known gotchas (see `clearpay_dashboard_methodology.md` for the full list)

1. **Bucket sums do not reconcile exactly to Total POS.** The residual is a mix of: (a) self-pay ∩ capped-bucket overlap — a self-pay patient who also got a copay/ded+coins estimate is counted both in Self-Pay (raw) and in the capped insurance bucket, (b) hidden overcollection on `zero_cost` and `other` bookings (not flowed into spillover), (c) `sum_refunds` that exceed `sum_paid_amount_pos` on rare bookings. For NextCare this residual is roughly ±$50K (~1% of Total POS). The waterfall no longer claims to reconcile visually — the Total POS row shows only the collected number, not a synthetic "shown" total.
2. **POS scope diverges from app** for bill-heavy partners. This dashboard uses `sum_paid_amount_pos - sum_refunds`; the app's `actual_billed_amount` uses `sum_paid_amount - sum_refunds` (POS + bill). For NextCare `sum_paid_amount_bill` is ~$0 so the numbers match. For partners with post-visit bill collection, call this out in the response and note that Total POS will be lower than what Observatory shows.
3. `sum_paid_amount_pos` is gross — always subtract `sum_refunds` and clamp at 0.
4. `dim_locations` PK is `id`, not `location_id`. Join `on b.location_id = l.id`.
5. Use `dbt_remote_mcp` (de-identified). No PHI fields needed.

## If the user wants a visual change

- **Different layout / KPI structure:** fine, edit `template.html` directly, but do not change the SQL semantics. The semantic rules above are non-negotiable — they are what makes the dashboard match the app.
- **Add a new component/bucket:** update the `bucket` CASE in the base CTE, add corresponding `shown`/`collected` aggregations, and add a waterfall row. Document the new bucket in the methodology doc.

## Companion reference

Full semantic rationale, app-to-dbt field mapping, and mistake-log from the original (broken) dashboard: `clearpay_dashboard_methodology.md`.
