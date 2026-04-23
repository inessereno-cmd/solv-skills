# ClearPay Collection Metrics Dashboard — SQL Methodology

Reference document for recreating the partner-level ClearPay collection metrics dashboard against the dbt warehouse. Aligned with `observatory_service.py` / `invoice_estimates.py` so dbt-derived numbers match what partners see in the Observatory product.

**Source of truth:** `solv/dapi/solv/data/query/invoice_estimates.py` → `observatory_dashboard()`. Captured in `observatory_dashboard_semantics.md` (the app-side spec). This document is the dbt translation layer.

---

## App → dbt field mapping

| App concept | dbt expression | Notes |
|---|---|---|
| `estimate_total` per booking | `cp.solv_estimate_in_network` | The in-network ClearPay estimate, in dollars |
| `estimate_type` per booking | `cp.estimate_type` | Already implements line-item classification logic in dbt |
| `actual_billed_amount` per booking (POS) | `case when cp.sum_paid_amount_pos > 0 then greatest(cp.sum_paid_amount_pos - coalesce(cp.sum_refunds, 0), 0) else null end` | NULL when no POS payment; net of refunds |
| `is_self_pay` per booking | `cp.estimate_type = 'self_pay' OR b.insurer_type in ('self-pay','selfPay')` | Broader than `estimate_type='self_pay'` alone |
| `estimate_failed` | `cp.estimate_failed` | Boolean |
| Booking universe | `b.status = 'discharged'` | Do **not** filter on `cp.has_payment` |

**Critical:** `cp.sum_paid_amount_pos` is **gross** (succeeded charges before refunds). The app uses `succeeded_amount − refunds`, so always subtract `cp.sum_refunds`.

**Critical:** Use `LEFT JOIN fact_bookings_clearpay_payments` — some discharged bookings have no `cp` row at all. INNER JOIN drops them and undercounts the universe by ~13%. Filtering on `has_payment=true` undercounts by ~47%.

**`cp.sum_refunds` caveat:** this column is total refunds across POS+bill (no separate POS refund column exists). For partners with material bill volume this can over-net the POS figure; clamp with `GREATEST(... , 0)`.

---

## Base CTE (parameterized)

Every dashboard query starts here. Swap `<group_id>` and the date range.

```sql
with base as (
    select
        b.id,
        b.local_appointment_date,
        b.location_id,
        l.state,
        l.display_name_secondary as clinic_name,
        cp.solv_estimate_in_network                                             as estimate_total,
        cp.estimate_type,
        cp.estimate_failed,
        case
            when cp.sum_paid_amount_pos > 0
                then greatest(cp.sum_paid_amount_pos - coalesce(cp.sum_refunds, 0), 0)
            else null
        end                                                                     as actual_billed,
        case
            when cp.estimate_type = 'self_pay'
              or b.insurer_type in ('self-pay', 'selfPay')
                then true
            else false
        end                                                                     as is_self_pay,
        case
            when cp.estimate_failed = true or cp.solv_estimate_in_network is null then 'failed_no_estimate'
            when cp.solv_estimate_in_network = 0                                  then 'zero_cost'
            when cp.estimate_type in ('copay','deductible','coinsurance','self_pay','zero_cost')
                                                                                  then cp.estimate_type
            else 'other'   -- catches dbt's 'mixed', 'other', 'fixed_amount', 'out_of_pocket_max_met'
        end                                                                     as bucket
    from {{ ref('dim_bookings') }} b
    inner join {{ ref('dim_locations') }} l on b.location_id = l.id
    left join {{ ref('fact_bookings_clearpay_payments') }} cp on b.id = cp.id
    where b.group_id = <group_id>
      and b.group_id not in (21, 12195)         -- exclude demo/test groups
      and b.status = 'discharged'
      and date(b.local_appointment_date) between '<start_date>' and '<end_date>'
)
```

---

## Bucket classification

Each booking is assigned to **exactly one** bucket based on `cp.estimate_type` (which the dbt model already derives from line items). Mirrors the `estimate_base` CASE expression in `invoice_estimates.py`.

| `bucket` value | Condition |
|---|---|
| `failed_no_estimate` | `cp.estimate_failed = true` OR `cp.solv_estimate_in_network is null` |
| `zero_cost` | `cp.solv_estimate_in_network = 0` |
| `copay` / `deductible` / `coinsurance` / `self_pay` | `cp.estimate_type` = one of these |
| `other` | dbt classifications dbt outputs but the app folds elsewhere: `mixed`, `other`, `fixed_amount`, `out_of_pocket_max_met` |

**Why `is_self_pay` is separate from `bucket = 'self_pay'`:** Some bookings have `b.insurer_type = 'self-pay'` but `cp.estimate_type` is null or set to a different bucket (e.g., copay). The app's `self_pay_collected_cents` aggregate filters on `is_self_pay`, not `estimate_type`. So we keep `is_self_pay` as a separate flag.

---

## KPI formulas

### Copay (capped)

```sql
sum(case when bucket = 'copay'
         then estimate_total else 0 end)                                                 as copay_shown,
sum(case when bucket = 'copay' and estimate_total is not null
         then least(coalesce(actual_billed, 0), estimate_total) else 0 end)              as copay_collected
```

### Deductible + Coinsurance (capped, **combined** per app)

```sql
sum(case when bucket in ('deductible','coinsurance')
         then estimate_total else 0 end)                                                 as ded_coins_shown,
sum(case when bucket in ('deductible','coinsurance') and estimate_total is not null
         then least(coalesce(actual_billed, 0), estimate_total) else 0 end)              as ded_coins_collected
```

The app combines these into a single KPI (`deductible_coinsurance_shown_cents` / `_collected_cents`). Don't split them.

### Self-Pay (RAW — not capped)

```sql
-- Shown is informational only; the app does NOT expose self_pay_shown_vs_collected
sum(case when bucket = 'self_pay'
         then estimate_total else 0 end)                                                 as self_pay_shown,

-- Collected is RAW: not capped, filtered by is_self_pay (which is broader than bucket)
sum(case when actual_billed is not null and is_self_pay = true
         then actual_billed else 0 end)                                                  as self_pay_collected_raw
```

### Spillover (overcollection above estimate)

For copay / ded+coins bookings only, the amount collected **above** the estimate. Self-pay isn't capped, so it has no spillover.

```sql
sum(case when actual_billed is not null
          and estimate_total is not null
          and bucket in ('copay','deductible','coinsurance')
         then greatest(actual_billed - estimate_total, 0) else 0 end)                    as overcollection_spillover
```

**Known limitation:** this does not include overcollection on `zero_cost` bookings (patients charged when estimate said $0) or on `'other'` bookings. For NextCare that's ~$68K hidden on zero_cost and ~$0.5K hidden on other — flagged in the review (Issue 1) but deliberately left out to keep the spillover metric focused on estimates that should have held.

### Other / Mixed (capped)

Bookings where `estimate_type` is `mixed`, `other`, `fixed_amount`, or `out_of_pocket_max_met` — the app folds these into copay/deductible/coinsurance/self_pay via its line-item priority logic, but we don't have access to that logic directly in dbt. Rather than mis-route them, surface them as their own row. Capped for consistency with copay/ded+coins.

```sql
sum(case when bucket = 'other'
         then estimate_total else 0 end)                                                 as other_shown,
sum(case when bucket = 'other' and estimate_total is not null
         then least(coalesce(actual_billed, 0), estimate_total) else 0 end)              as other_collected
```

Typically ~0.5–1% of Total POS. Shown in the waterfall as "Other / Mixed"; not displayed in the locations table (kept off to avoid table-width bloat) but included in the CSV export.

### No-estimate revenue (insured patients)

POS dollars collected on bookings where ClearPay never produced an estimate (failed, RTE down, no insurance card, etc.), **excluding self-pay bookings**. Self-pay patients legitimately don't get RTE, and their collections are already counted in `self_pay_collected_raw` — including them in "no RTE" double-counts ~$193K for NextCare over 30 days.

The app surfaces this in the "no_estimate_no_copay" / "no_estimate_has_copay" reasons; we present it as an operational signal ("where RTE isn't firing for insured patients who should have gotten an estimate").

```sql
sum(case when actual_billed is not null
          and estimate_total is null
          and is_self_pay = false
         then actual_billed else 0 end)                                                  as no_estimate_insured_collected
```

### Volume

```sql
count(*)                                                                                 as bookings_total,
sum(case when estimate_total is not null then 1 else 0 end)                              as bookings_with_estimate,
sum(coalesce(actual_billed, 0))                                                          as total_pos_collected
```

---

## Standard aggregations

### Top-level totals

```sql
-- (insert base CTE here)
select
    count(*)                                                                             as bookings_total,
    sum(case when estimate_total is not null then 1 else 0 end)                          as bookings_with_estimate,
    sum(coalesce(actual_billed, 0))                                                      as total_pos_collected,
    sum(case when bucket = 'copay'                          then estimate_total else 0 end)                  as copay_shown,
    sum(case when bucket = 'copay' and estimate_total is not null
             then least(coalesce(actual_billed, 0), estimate_total) else 0 end)                              as copay_collected,
    sum(case when bucket in ('deductible','coinsurance')    then estimate_total else 0 end)                  as ded_coins_shown,
    sum(case when bucket in ('deductible','coinsurance') and estimate_total is not null
             then least(coalesce(actual_billed, 0), estimate_total) else 0 end)                              as ded_coins_collected,
    sum(case when bucket = 'self_pay'                       then estimate_total else 0 end)                  as self_pay_shown,
    sum(case when actual_billed is not null and is_self_pay = true
             then actual_billed else 0 end)                                                                  as self_pay_collected_raw,
    -- Other / Mixed (Issue 3 fix): capped, surfaces bookings the app would re-route via line-item priority
    sum(case when bucket = 'other'                          then estimate_total else 0 end)                  as other_shown,
    sum(case when bucket = 'other' and estimate_total is not null
             then least(coalesce(actual_billed, 0), estimate_total) else 0 end)                              as other_collected,
    sum(case when actual_billed is not null and estimate_total is not null
              and bucket in ('copay','deductible','coinsurance')
             then greatest(actual_billed - estimate_total, 0) else 0 end)                                    as overcollection_spillover,
    -- No-RTE on insured patients only (Issue 2 fix): excludes is_self_pay = true
    sum(case when actual_billed is not null and estimate_total is null
              and is_self_pay = false
             then actual_billed else 0 end)                                                                  as no_estimate_insured_collected
from base
```

### Daily breakdown

Add `group by date(b.local_appointment_date)` to the same select. Reference column: `appt_date`.

### Location breakdown

Add `group by l.state, l.display_name_secondary` to the same select.

---

## Known semantic gotchas

1. **Components still don't sum to Total POS — but the residual is smaller and documented.** The residual mix after the four dashboard fixes (see "Dashboard fixes" section below):
   - **Self-pay ∩ capped-bucket overlap (~$21K for NextCare, ~0.4%):** a self-pay patient who also got a copay/ded+coins estimate is counted both in Self-Pay (raw) and in the capped insurance bucket. Matches the app. Not worth resolving.
   - **Hidden overcollection on `zero_cost` and `'other'` bookings (~$68K for NextCare, ~1.2%):** spillover only captures copay/ded+coins overcollection. Zero-cost overcollection (patient charged when estimate said $0) and 'other'-bucket overcollection are collected into Total POS but not into any sub-bucket. Flagged as Issue 1 in the review; not fixed to keep spillover focused on broken estimates.
   - **`sum_refunds` > `sum_paid_amount_pos` on rare bookings:** clamped to 0 by `GREATEST(... , 0)`. For NextCare this explained a $265 gap for a single booking.

   The Total POS waterfall row now shows only the collected number — no synthetic "shown" total, no "(including no estimate)" annotation — so the arithmetic is honest: each sub-bucket reconciles internally, and Total POS stands alone as the ground-truth aggregate.

2. **POS-only scope diverges from the app for bill-heavy partners.** `actual_billed` in this dashboard uses `sum_paid_amount_pos - sum_refunds`. The app's `actual_billed_amount` uses `sum_paid_amount - sum_refunds` (POS + bill). For NextCare `sum_paid_amount_bill = $0` so the two are equivalent. For any partner with meaningful post-visit bill collection, the dashboard's Total POS will be **lower** than what Observatory reports. Call this out when generating the dashboard for a bill-heavy partner — offer to switch the SQL to `sum_paid_amount` if they want app-parity instead of POS-scope.

3. **Self-pay shown vs collected ratios look strange.** Self-pay shown uses `bucket='self_pay'` but self-pay collected uses the broader `is_self_pay` filter. The denominators don't match. The app exposes self-pay collected as a raw aggregate without a paired "shown" KPI for this exact reason. If you need a comparable rate, scope shown the same way: `sum(case when is_self_pay then estimate_total else 0 end)`.

4. **`sum_paid_amount_pos` is gross, not net.** The dbt column does not subtract refunds. Always wrap with `greatest(sum_paid_amount_pos - coalesce(sum_refunds, 0), 0)` when computing what the patient effectively paid.

5. **`actual_billed` is NULL when no POS payment, not 0.** Inside `LEAST()` you need `coalesce(actual_billed, 0)` to avoid NULL-propagating to the cap. Inside `SUM()` you can keep it NULL (SUM ignores).

6. **`b.insurer_type` has multiple self-pay spellings.** Use `in ('self-pay','selfPay')`. Don't use `like`.

7. **`cp.sum_refunds` mixes POS and bill refunds.** No POS-only refund column exists in `fact_bookings_clearpay_payments`. For partners with significant bill payment volume, this can over-net the POS figure. The `greatest(... , 0)` clamp prevents negatives but can't perfectly attribute. Acceptable for partner reporting; flag if precision matters. (Issue 6 in the review — not fixed, cosmetic for NextCare.)

8. **`dim_locations` PK is `id`, not `location_id`.** Join `on b.location_id = l.id`. The display name is `l.display_name_secondary`.

9. **`dim_groups` PK is `group_id`, not `id`.** This is the only mart that breaks the `id` convention.

10. **Don't include `solv.dbt.dim_groups` filter on `g.is_active`.** ClearPay-relevant groups can be in transition states; rely on `b.group_id NOT IN (21, 12195)` (demo exclusion) instead.

---

## Dashboard fixes (2026-04-22 review round)

After the first rebuild matched the app's core semantics, a formal review surfaced six issues. Four were fixed; two were deliberately left as documented known limitations.

| # | Issue | Fix | Impact on NextCare |
|---|---|---|---|
| 2 | Self-pay ∩ no-estimate double-counted | Added `AND is_self_pay = false` to `no_estimate_collected` → renamed `no_estimate_insured_collected`. The "No RTE" KPI card is now labeled "Revenue collected where no RTE is run (insured patients)". | "No RTE" dropped from $1.87M → $1.67M. Cleaner metric (RTE doesn't apply to self-pay anyway). |
| 3 | ~$32K in `'other'` bucket (mixed / oop_max_met / fixed_amount / other) was invisible | Added `other_shown` / `other_collected` columns (capped, like copay/ded+coins) and surfaced as an "Other / Mixed" row in the waterfall. Not added to the locations table (kept compact) but included in CSV export. | Surfaces $30.6K collected / $44.4K shown (68.9%). |
| 4 | "Total POS Collected" label misleading for bill-heavy partners | Kept POS-only scope (`sum_paid_amount_pos - sum_refunds`) and kept the label. For bill-heavy partners, this diverges from app's `actual_billed_amount`. Documented in SKILL.md known gotchas and flagged here. | No change for NextCare (bill ≈ $0). Future bill-heavy partners need a heads-up. |
| 5 | Waterfall "Total POS shown" cell was arithmetically bogus (summed incompatible components) | Removed the Shown cell from the Total POS row and removed the "(including no estimate)" annotation. The Total POS row now shows only the collected number. | Dashboard is more honest about reconciliation gaps — no implied arithmetic identity. |

**Not fixed (documented as known limitations):**

- **Issue 1: `zero_cost` overcollection invisible.** Spillover only captures copay/ded+coins. Zero-cost bookings charged above $0 ($68K for NextCare over 30 days, ~1,262 bookings) are collected in Total POS but not surfaced. Keep an eye on this for partners with high zero-cost charging.
- **Issue 6: `sum_refunds` mixes POS + bill refunds.** For NextCare this is cosmetic (bill refunds ≈ 0). For bill-heavy partners the POS figure can be over-netted by bill refunds.

---

## Mistakes the previous (broken) dashboard made

For posterity — these are the bugs that motivated this rewrite. If you see these patterns elsewhere, treat them as red flags.

| Bug | Effect | Fix |
|---|---|---|
| Filtered booking universe to `cp.has_payment = true` | Dropped ~47% of discharged bookings | Use all discharged bookings via LEFT JOIN |
| Used `INNER JOIN fact_bookings_clearpay_payments` | Dropped bookings with no `cp` row at all (~13% additional) | LEFT JOIN |
| Used `LEAST(sum_paid_amount_pos, estimate_<line_item>_amount)` per line item | Caps at line-item amount instead of full estimate; doesn't match app's single-bucket assignment | Cap at `estimate_total` (full `solv_estimate_in_network`) per `bucket` |
| Treated copay / deductible / coinsurance as separate KPIs | App combines deductible + coinsurance | Combine `bucket in ('deductible','coinsurance')` |
| Used `LEAST()` cap on self-pay | Undercounted self-pay collected by ~4× | Self-pay is RAW (uncapped) |
| Filtered self-pay only by `estimate_type = 'self_pay'` | Missed bookings with `b.insurer_type = 'self-pay'` and no estimate | Use `is_self_pay = (estimate_type='self_pay' OR insurer_type in ('self-pay','selfPay'))` |
| Used gross `sum_paid_amount_pos` without subtracting `sum_refunds` | Overstated collected for partners with refund activity | Subtract refunds, clamp with `GREATEST(... , 0)` |

---

## Parameter cheatsheet

To rebuild the dashboard for any partner / date window:

| Parameter | Where | Example |
|---|---|---|
| Group ID | `b.group_id = <group_id>` | NextCare = `13`. Find via `dim_groups.group_name` |
| Start date | `between '<start_date>' and ...` | `'2026-03-19'` |
| End date | `... and '<end_date>'` | `'2026-04-17'` |
| Aggregation grain | `group by ...` | none = totals; `date(...)` = daily; `state, clinic_name` = location |

Connector: **`dbt_remote_mcp`** (de-identified — no PHI fields needed for this dashboard).

---

*Last updated: 2026-04-22*
*Source app code: `solv/dapi/solv/data/query/invoice_estimates.py` (`observatory_dashboard`)*
*Source spec: `observatory_dashboard_semantics.md`*
