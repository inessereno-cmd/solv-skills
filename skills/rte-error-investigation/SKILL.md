---
name: rte-error-investigation
description: Analyze RTE errors from dbt and generate Slack to-do messages for investigation. Queries RTE error data directly from dbt models for discharged bookings with failed RTE attempts. Produces analysis by group/clinic, by payer, and by error type, each with booking ID examples. Generates a Slack message with top 7 payers needing attention and top 5 worst-performing partners for report-out. Sends directly to Slack DM.
---

# RTE Error Investigation To-Do Generator

Query RTE error data from dbt and generate investigation to-do list for Slack.

## Input Required

**Date Range Parameters:**
- Start date (default: 2 days ago)
- End date (default: today)

## Workflow

1. Run SQL queries via dbt MCP to aggregate RTE error data
2. Generate formatted Slack message with investigation priorities
3. Send to user's Slack DM using Zapier slack_send_direct_message

## Using the Script

```python
from scripts.analyze_rte_errors import run_full_analysis, generate_slack_message

# Run full analysis with date range
results = run_full_analysis(
    start_date="2026-02-04",  # Default: 2 days ago
    end_date="2026-02-06"      # Default: today
)

# Access aggregated results (each includes up to 5 booking ID examples):
# - results['by_group_clinic']: Errors by group, then by clinic within group
# - results['error_by_group']: Error types by group
# - results['by_payer']: Total errors by payer
# - results['error_by_payer']: Error types by payer

# Get formatted Slack message (top 7 payers, top 5 partners)
slack_msg = results['slack_message']

# Or customize counts:
slack_msg = generate_slack_message(results, top_payers=7, top_partners=5)
```

## Output: Slack Message Structure

**TO-DO Section** — Top 7 payers with most errors:
- Payer name and error count
- Top 3 error types for that payer
- 5 booking IDs to investigate

**REPORT-OUT Section** — Top 5 worst-performing partners:
- Partner name and total errors
- Top 3 clinics by error count
- Top 3 error types with booking IDs to investigate

## Sending to Slack

Use Zapier `slack_send_direct_message` tool with the generated message text.

## Implementation Notes for Claude

When using this skill:

1. **Import the analysis script:**
   ```python
   import sys
   sys.path.append('/mnt/skills/user/rte-error-investigation')
   from scripts.analyze_rte_errors import (
       run_full_analysis, 
       structure_by_group_clinic,
       structure_by_payer,
       structure_error_by_group,
       structure_error_by_payer,
       generate_slack_message
   )
   ```

2. **Get SQL queries for date range:**
   ```python
   analysis_config = run_full_analysis(start_date='2026-02-04', end_date='2026-02-06')
   queries = analysis_config['queries']
   ```

3. **Execute each query via dbt MCP:**
   Use `dbt_remote_mcp:execute_sql` tool for each query in the queries dict.

4. **Structure the results:**
   - `structure_by_group_clinic()` for group/clinic query results
   - `structure_by_payer()` for payer query results
   - `structure_error_by_group()` for error by group query results
   - `structure_error_by_payer()` for error by payer query results

5. **Calculate total errors:**
   Sum all error counts from the by_payer results.

6. **Generate Slack message:**
   ```python
   results = {
       'by_group_clinic': structured_group_clinic,
       'by_payer': structured_payer,
       'error_by_group': structured_error_by_group,
       'error_by_payer': structured_error_by_payer,
       'total_errors': total_count
   }
   slack_msg = generate_slack_message(results, top_payers=7, top_partners=5)
   ```

7. **Send to Slack:**
   Use Zapier `slack_send_direct_message` with the slack_msg text.

## SQL Query Details

All queries use a common base CTE that:
- Filters for discharged bookings in the date range
- Requires RTE attempt was made but failed
- Excludes government insurance (Tricare, Medicaid)
- Excludes DOT/work/employment physicals (urgent care only)
- Maps AAA error codes to readable descriptions
- Requires valid member_code (insurance ID)

Each aggregation query:
- Groups by relevant dimensions (payer, group, clinic, error_type)
- Counts errors
- Collects up to 5 example booking IDs using ARRAY_AGG
- Orders results by error count descending
