"""
ClearPay Collection Metrics Dashboard — daily data refresh.
Uses the dbt Cloud MCP API. Generates ines/ClearPay_Collection_Metrics_NextCare_Discharged.html
"""

import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import urllib.request

ROOT = Path(__file__).parent.parent
PARTNER_NAME = "NextCare"
GROUP_ID = 13
TEMPLATE = ROOT / "ines" / "clearpay-collections-template.html"
OUTPUT = ROOT / "ines" / "ClearPay_Collection_Metrics_NextCare_Discharged.html"

def load_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()

DBT_URL = "https://eo424.us1.dbt.com/api/ai/v1/mcp/"
DBT_HEADERS = {
    "Authorization": f"token {os.environ['DBT_API_TOKEN']}",
    "x-dbt-prod-environment-id": os.getenv("DBT_PROD_ENV_ID", "129791"),
    "x-dbt-dev-environment-id": os.getenv("DBT_DEV_ENV_ID", "112599"),
    "x-dbt-user-id": os.getenv("DBT_USER_ID", "192793"),
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

def get_date_range(days=30):
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return str(start), str(end)

def execute_sql(sql, request_id=1):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "execute_sql", "arguments": {"sql": sql}},
        "id": request_id,
    }).encode()
    req = urllib.request.Request(DBT_URL, data=payload, headers=DBT_HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode()
    for line in raw.splitlines():
        if line.startswith("data:"):
            envelope = json.loads(line[5:].strip())
            if "error" in envelope:
                raise RuntimeError(f"dbt error: {envelope['error']}")
            result = json.loads(envelope["result"]["content"][0]["text"])
            if not result.get("data"):
                return []
            fields = [f["name"] for f in result["schema"]["fields"]]
            return [[row.get(f) for f in fields] for row in result["data"]]
    raise RuntimeError(f"No data in response: {raw[:200]}")

BASE_CTE = """
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
    from {{{{ ref('dim_bookings') }}}} b
    inner join {{{{ ref('dim_locations') }}}} l on b.location_id = l.id
    left join {{{{ ref('fact_bookings_clearpay_payments') }}}} cp on b.id = cp.id
    where b.group_id = {group_id}
      and b.group_id not in (21, 12195)
      and b.status = 'discharged'
      and date(b.local_appointment_date) between '{start_date}' and '{end_date}'
)
"""

SELECT_LIST = """
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
    round(sum(case when bucket = 'other'                          then estimate_total else 0 end), 2)            as other_shown,
    round(sum(case when bucket = 'other' and estimate_total is not null
             then least(coalesce(actual_billed, 0), estimate_total) else 0 end), 2)                              as other_collected,
    round(sum(case when actual_billed is not null and estimate_total is not null
              and bucket in ('copay','deductible','coinsurance')
             then greatest(actual_billed - estimate_total, 0) else 0 end), 2)                                    as overcollection_spillover,
    round(sum(case when actual_billed is not null and estimate_total is null
              and is_self_pay = false
             then actual_billed else 0 end), 2)                                                                  as no_estimate_insured_collected
from base
"""

def build_queries(group_id, start_date, end_date):
    cte = BASE_CTE.format(group_id=group_id, start_date=start_date, end_date=end_date)
    totals_q  = cte + "select" + SELECT_LIST
    daily_q   = cte + "select appt_date," + SELECT_LIST + "group by appt_date order by appt_date"
    locs_q    = cte + "select state, clinic_name," + SELECT_LIST + "group by state, clinic_name order by state, clinic_name"
    return totals_q, daily_q, locs_q

def fmt_date(d):
    """2026-03-24 → Mar 24, 2026"""
    from datetime import datetime
    return datetime.strptime(d, "%Y-%m-%d").strftime("%b %-d, %Y")

def build_html(totals_row, daily_rows, loc_rows, start_date, end_date):
    template = TEMPLATE.read_text(encoding="utf-8")

    # Daily JSON: [dt, bookings_total, bookings_with_estimate, total_pos,
    #              copay_shown, copay_collected, dc_shown, dc_collected,
    #              sp_shown, sp_collected_raw, other_shown, other_collected,
    #              spillover, no_estimate_insured]
    daily_json = []
    for row in daily_rows:
        daily_json.append([str(row[0])] + [float(v) if v is not None else 0 for v in row[1:]])

    # Locations JSON: [state, clinic_name, bookings_total, ...]
    locs_json = []
    for row in loc_rows:
        locs_json.append([str(row[0]), str(row[1])] + [float(v) if v is not None else 0 for v in row[2:]])

    html = template
    html = html.replace("__DAILY_JSON__", json.dumps(daily_json))
    html = html.replace("__LOCATIONS_JSON__", json.dumps(locs_json))
    html = html.replace("<!-- PARTNER_NAME -->", PARTNER_NAME)
    html = html.replace("<!-- DATE_RANGE -->", f"{fmt_date(start_date)} – {fmt_date(end_date)}")
    html = html.replace("<!-- END_DATE -->", end_date)
    html = html.replace("<!-- CSV_FILENAME -->",
                        f"clearpay-nextcare-{start_date}-to-{end_date}.csv")
    html = html.replace("<!-- GENERATED_DATE -->", str(date.today()))
    return html

def main():
    start_date, end_date = get_date_range(days=30)
    print(f"Refreshing ClearPay Collection Metrics: {start_date} → {end_date}")

    totals_q, daily_q, locs_q = build_queries(GROUP_ID, start_date, end_date)

    print("  Running totals query...")
    totals = execute_sql(totals_q, request_id=1)
    print(f"  Running daily query...")
    daily  = execute_sql(daily_q,  request_id=2)
    print(f"  Running locations query...")
    locs   = execute_sql(locs_q,   request_id=3)

    print(f"  Building HTML ({len(daily)} days, {len(locs)} locations)...")
    html = build_html(totals[0] if totals else [], daily, locs, start_date, end_date)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"  Saved → {OUTPUT.name}")
    print(f"Done. Data through {end_date}.")

if __name__ == "__main__":
    main()
