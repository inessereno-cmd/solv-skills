"""
NextCare ClearPay Observatory — daily data refresh.
Reads credentials from ../.env, connects to localhost Redshift tunnel,
updates ines/nextcare-clearpay-observatory.html with the last 30 days of data.
"""

import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent

def load_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def get_date_range(days=30):
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return str(start), str(end)

def run_query(cursor, sql, start_date, end_date, group_id=13):
    sql = sql\
        .replace("{START_DATE}", start_date)\
        .replace("{END_DATE}", end_date)\
        .replace("{GROUP_ID}", str(group_id))
    cursor.execute(sql)
    rows = []
    for row in cursor.fetchall():
        rows.append([str(v) if hasattr(v, "isoformat") else v for v in row])
    return rows

def inject(html_path, var_name, rows):
    content = html_path.read_text(encoding="utf-8")
    pattern = rf"const {var_name} = \[[\s\S]*?\];"
    replacement = f"const {var_name} = {json.dumps(rows)};"
    if not re.search(pattern, content):
        print(f"  WARNING: {var_name} not found in HTML — skipping", file=sys.stderr)
        return
    content = re.sub(pattern, replacement, content)
    html_path.write_text(content, encoding="utf-8")
    print(f"  {var_name}: {len(rows)} rows")

QUERIES = {
    "RAW_DAILY": """
        WITH daily_bookings AS (
          SELECT calendar_date, SUM(total_bookings) as total_bookings
          FROM solv.dbt.fact_location_daily
          WHERE group_id = {GROUP_ID}
            AND calendar_date BETWEEN '{START_DATE}' AND '{END_DATE}'
          GROUP BY calendar_date
        ),
        daily_estimates AS (
          SELECT
            CAST(cp.booking_created_date AS DATE) as dt,
            SUM(CASE WHEN cp.has_estimate THEN 1 ELSE 0 END) as estimate_generated,
            SUM(CASE WHEN cp.has_estimate AND cp.solv_estimate_in_network > 0 THEN 1 ELSE 0 END) as non_zero_estimate,
            SUM(CASE WHEN cp.is_eligible_estimate_for_charge THEN 1 ELSE 0 END) as estimate_charged,
            SUM(CASE WHEN cp.is_charged_exact_estimate THEN 1 ELSE 0 END) as exact_match,
            SUM(CASE WHEN cp.is_copay_line_item THEN 1 ELSE 0 END) as copay_total,
            SUM(CASE WHEN cp.is_copay_line_item AND cp.is_charged_exact_estimate THEN 1 ELSE 0 END) as copay_matched,
            SUM(CASE WHEN cp.is_deductible_line_item THEN 1 ELSE 0 END) as deductible_total,
            SUM(CASE WHEN cp.is_deductible_line_item AND cp.is_charged_exact_estimate THEN 1 ELSE 0 END) as deductible_matched,
            SUM(CASE WHEN cp.is_coinsurance_line_item THEN 1 ELSE 0 END) as coinsurance_total,
            SUM(CASE WHEN cp.is_coinsurance_line_item AND cp.is_charged_exact_estimate THEN 1 ELSE 0 END) as coinsurance_matched,
            SUM(CASE WHEN cp.is_self_pay_line_item THEN 1 ELSE 0 END) as self_pay_total,
            SUM(CASE WHEN cp.is_self_pay_line_item AND cp.is_charged_exact_estimate THEN 1 ELSE 0 END) as self_pay_matched,
            SUM(CASE WHEN cp.estimate_is_zero_cost THEN 1 ELSE 0 END) as zero_cost_total,
            SUM(CASE WHEN cp.estimate_is_zero_cost AND cp.is_charged_exact_estimate THEN 1 ELSE 0 END) as zero_cost_matched,
            SUM(CASE WHEN cp.has_estimate
                      AND NOT COALESCE(cp.is_copay_line_item, FALSE)
                      AND NOT COALESCE(cp.is_deductible_line_item, FALSE)
                      AND NOT COALESCE(cp.is_coinsurance_line_item, FALSE)
                      AND NOT COALESCE(cp.is_self_pay_line_item, FALSE)
                      AND NOT COALESCE(cp.estimate_is_zero_cost, FALSE)
                 THEN 1 ELSE 0 END) as other_total,
            SUM(CASE WHEN cp.is_copay_line_item AND cp.is_eligible_estimate_for_charge THEN 1 ELSE 0 END) as copay_charged,
            SUM(CASE WHEN cp.is_deductible_line_item AND cp.is_eligible_estimate_for_charge THEN 1 ELSE 0 END) as deductible_charged,
            SUM(CASE WHEN cp.is_coinsurance_line_item AND cp.is_eligible_estimate_for_charge THEN 1 ELSE 0 END) as coinsurance_charged,
            SUM(CASE WHEN cp.is_self_pay_line_item AND cp.is_eligible_estimate_for_charge THEN 1 ELSE 0 END) as self_pay_charged
          FROM solv.dbt.fact_bookings_clearpay_payments cp
          JOIN solv.dbt.dim_locations l ON cp.location_id = l.id
          WHERE l.group_id = {GROUP_ID}
            AND CAST(cp.booking_created_date AS DATE) BETWEEN '{START_DATE}' AND '{END_DATE}'
          GROUP BY CAST(cp.booking_created_date AS DATE)
        )
        SELECT
          db.calendar_date, db.total_bookings,
          COALESCE(de.estimate_generated, 0), COALESCE(de.non_zero_estimate, 0),
          COALESCE(de.estimate_charged, 0), COALESCE(de.exact_match, 0),
          COALESCE(de.copay_total, 0), COALESCE(de.copay_matched, 0),
          COALESCE(de.deductible_total, 0), COALESCE(de.deductible_matched, 0),
          COALESCE(de.coinsurance_total, 0), COALESCE(de.coinsurance_matched, 0),
          COALESCE(de.self_pay_total, 0), COALESCE(de.self_pay_matched, 0),
          COALESCE(de.zero_cost_total, 0), COALESCE(de.zero_cost_matched, 0),
          COALESCE(de.other_total, 0),
          COALESCE(de.copay_charged, 0), COALESCE(de.deductible_charged, 0),
          COALESCE(de.coinsurance_charged, 0), COALESCE(de.self_pay_charged, 0)
        FROM daily_bookings db
        LEFT JOIN daily_estimates de ON db.calendar_date = de.dt
        ORDER BY db.calendar_date
    """,

    "RAW_LOCATIONS": """
        SELECT
          CAST(cp.booking_created_date AS DATE) as dt,
          l.state, l.name as clinic,
          COUNT(*) as bookings,
          SUM(CASE WHEN cp.has_estimate THEN 1 ELSE 0 END) as with_est,
          SUM(CASE WHEN cp.is_charged_exact_estimate THEN 1 ELSE 0 END) as exact,
          ROUND(SUM(COALESCE(cp.sum_paid_amount_pos, 0))::numeric, 2) as collected,
          ROUND(SUM(CASE WHEN cp.has_estimate AND cp.solv_estimate_in_network > 0
                    THEN GREATEST(cp.solv_estimate_in_network - COALESCE(cp.sum_paid_amount_pos, 0), 0)
                    ELSE 0 END)::numeric, 2) as missed
        FROM solv.dbt.fact_bookings_clearpay_payments cp
        JOIN solv.dbt.dim_locations l ON cp.location_id = l.id
        WHERE l.group_id = {GROUP_ID}
          AND CAST(cp.booking_created_date AS DATE) BETWEEN '{START_DATE}' AND '{END_DATE}'
        GROUP BY CAST(cp.booking_created_date AS DATE), l.state, l.name
        ORDER BY dt, l.state, l.name
    """,

    "RAW_OVERRIDES": """
        SELECT
          CAST(cp.booking_created_date AS DATE) as dt,
          CASE
            WHEN LOWER(ch.reason_for_manual_charge) LIKE '%incorrect%'
              OR LOWER(ch.reason_for_manual_charge) LIKE '%clearpayestimateincorrect%' THEN 'Estimate Incorrect'
            WHEN LOWER(ch.reason_for_manual_charge) LIKE '%partial%' THEN 'Partial Payment'
            WHEN LOWER(ch.reason_for_manual_charge) LIKE '%previous%'
              OR LOWER(ch.reason_for_manual_charge) LIKE '%prior%' THEN 'Previous Balance'
            WHEN LOWER(ch.reason_for_manual_charge) LIKE '%copay%' THEN 'Copay Override'
            WHEN LOWER(ch.reason_for_manual_charge) LIKE '%mdp%' THEN 'MDP Sign Up'
            WHEN LOWER(ch.reason_for_manual_charge) LIKE '%self%pay%' THEN 'Self Pay'
            WHEN ch.reason_for_manual_charge IS NULL
              OR TRIM(ch.reason_for_manual_charge) = '' THEN 'No reason provided'
            ELSE 'Other'
          END as reason,
          COUNT(DISTINCT cp.id) as cnt,
          ROUND(AVG(cp.solv_estimate_in_network)::numeric, 2) as avg_est,
          ROUND(AVG(cp.sum_paid_amount_pos)::numeric, 2) as avg_chg,
          ROUND(AVG(COALESCE(cp.sum_paid_amount_pos, 0) - cp.solv_estimate_in_network)::numeric, 2) as avg_delta
        FROM solv.dbt.fact_bookings_clearpay_payments cp
        JOIN solv.dbt.dim_locations l ON cp.location_id = l.id
        JOIN postgres.invoices inv ON inv.booking_id = cp.id AND inv.invoice_type = 'pos'
        JOIN postgres.charges ch ON ch.invoice_id = inv.id AND ch.status = 'succeeded'
        WHERE l.group_id = {GROUP_ID}
          AND CAST(cp.booking_created_date AS DATE) BETWEEN '{START_DATE}' AND '{END_DATE}'
          AND cp.has_estimate = TRUE
          AND NOT cp.is_charged_exact_estimate
        GROUP BY 1, 2
        ORDER BY dt, cnt DESC
    """,

    "RAW_INSPECTOR": """
        SELECT
          CAST(cp.id AS VARCHAR) as booking_id,
          CAST(CAST(cp.booking_created_date AS DATE) AS VARCHAR) as dt,
          l.name as clinic,
          '' as patient_name,
          CASE WHEN ib.most_recent_insurance_benefits_id IS NOT NULL THEN '1' ELSE '0' END as ins_card,
          CASE WHEN rte.is_real_time_eligibility_success THEN '1' ELSE '0' END as rte_success,
          CASE WHEN ib.primary_insurance_latest_success_copay_in_network IS NOT NULL
               THEN CAST(ib.primary_insurance_latest_success_copay_in_network AS VARCHAR)
               ELSE '' END as copay_rte,
          COALESCE(CAST(cp.estimate_copay_amount AS VARCHAR), '') as copay_comp,
          COALESCE(CAST(cp.estimate_coinsurance_amount AS VARCHAR), '') as coins_comp,
          COALESCE(CAST(cp.estimate_deductible_amount AS VARCHAR), '') as ded_comp,
          COALESCE(CAST(cp.solv_estimate_in_network AS VARCHAR), '0') as total_est,
          COALESCE(CAST(cp.sum_paid_amount_pos AS VARCHAR), '0') as pos_charged,
          CASE WHEN cp.is_self_pay_line_item THEN '1' ELSE '0' END as is_self_pay,
          COALESCE(ib.primary_insurance_returned_payer_name, '') as payer_name
        FROM solv.dbt.fact_bookings_clearpay_payments cp
        JOIN solv.dbt.dim_locations l ON cp.location_id = l.id
        LEFT JOIN solv.dbt.fact_bookings_insurance_benefits_latest ib ON cp.id = ib.id
        LEFT JOIN solv.dbt.int_bookings_rte_success_flag rte ON cp.id = rte.id
        WHERE l.group_id = {GROUP_ID}
          AND CAST(cp.booking_created_date AS DATE) BETWEEN '{START_DATE}' AND '{END_DATE}'
        ORDER BY cp.booking_created_date, l.name, cp.id
    """,

    "RAW_COLLECTIONS": """
        SELECT
          CAST(fld.calendar_date AS VARCHAR) as dt,
          ROUND(SUM(fld.solv_pay_total_paid)::numeric, 2) as total_paid,
          ROUND((SUM(fld.solv_pay_total_paid) / NULLIF(SUM(fld.total_bookings), 0))::numeric, 1) as avg_per_booking,
          ROUND(SUM(fld.solv_pay_total_paid_facesheet)::numeric, 2) as paid_facesheet,
          ROUND(SUM(fld.solv_pay_total_paid_autocollect)::numeric, 2) as paid_autocollect,
          ROUND(SUM(fld.solv_pay_total_paid_terminal)::numeric, 2) as paid_terminal,
          ROUND(SUM(fld.solv_pay_total_paid_sms)::numeric, 2) as paid_sms,
          0.0 as paid_other,
          SUM(fld.discharged_bookings_pos_invoices_created) as pos_invoices,
          SUM(fld.total_bookings) as total_bookings
        FROM solv.dbt.fact_location_daily fld
        WHERE fld.group_id = {GROUP_ID}
          AND fld.calendar_date BETWEEN '{START_DATE}' AND '{END_DATE}'
        GROUP BY fld.calendar_date
        ORDER BY fld.calendar_date
    """,
}

def main():
    load_env()

    host = os.getenv("REDSHIFT_HOST", "localhost")
    port = int(os.getenv("REDSHIFT_PORT", "5439"))
    user = os.environ["REDSHIFT_USER"]
    password = os.environ["REDSHIFT_PASSWORD"]
    dbname = os.getenv("REDSHIFT_DBNAME", "solv")

    start_date, end_date = get_date_range()
    print(f"Refreshing observatory: {start_date} → {end_date}")

    try:
        import redshift_connector
        conn = redshift_connector.connect(
            host=host, database=dbname, port=port, user=user, password=password
        )
    except ImportError:
        import psycopg2
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password, dbname=dbname
        )

    html_path = ROOT / "ines" / "nextcare-clearpay-observatory.html"
    cursor = conn.cursor()

    for var_name, sql in QUERIES.items():
        print(f"  Querying {var_name}...")
        try:
            rows = run_query(cursor, sql, start_date, end_date)
            inject(html_path, var_name, rows)
        except Exception as e:
            print(f"  ERROR on {var_name}: {e}", file=sys.stderr)

    cursor.close()
    conn.close()
    print(f"Done. Data through {end_date}.")

if __name__ == "__main__":
    main()
