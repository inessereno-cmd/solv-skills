---
name: account-risk-check
description: Run a customer account risk audit. Pulls top accounts by ARR from HubSpot, scans recent Gong/Grain call transcripts for churn signals, cross-references Slack channel mentions, and outputs a ranked risk report saved to a dated markdown file. Use when asked to "check account health", "run a risk scan", "which accounts are at risk", "churn risk report", or "account risk check". Trigger on: account risk, churn signals, customer health, at-risk accounts, retention scan.
---

# Account Risk Check

Scans your top accounts for churn risk by combining CRM data, call transcripts, and Slack signals into a ranked markdown report.

## Parameters

Accept these from the user prompt (use defaults if not specified):
- `count` — number of accounts to scan (default: **20**)
- `window_days` — how far back to scan calls and Slack (default: **30**)
- `slack_channel` — Slack channel to search (default: **#partner-success**)

## Workflow

Work through these steps in order. Do not skip steps or ask the user for confirmation between them — just run and report at the end.

### Step 1: Pull Top Accounts by ARR

Use the HubSpot MCP (`mcp__claude_ai_HubSpot__search_crm_objects`) to fetch the top `count` closed-won deals sorted by amount descending.

```
objectType: deals
filterGroups:
  - filters:
      - propertyName: dealstage, operator: EQ, value: closedwon
      - propertyName: amount, operator: HAS_PROPERTY
properties: [dealname, amount, hubspot_owner_id, closedate, hs_object_id]
sorts: [{ propertyName: amount, direction: DESCENDING }]
limit: <count>
```

Extract: account name, deal amount (= ARR proxy), deal ID, owner. These are your accounts to scan.

### Step 2: Pull Call Transcripts

For each account, search for recent call recordings using the **Grain skill** (`/grain`) or the Gong MCP if available. Search by account name, limit to the last `window_days` days, and retrieve up to 3 calls per account.

If using Grain: search by company name, filter by date, pull transcript text.
If Gong MCP is authenticated: use it to search calls associated with the account.

If no calls are found for an account, note "No recent calls" and continue — don't skip the account entirely.

### Step 3: Scan for Risk Signals

For each call transcript, scan the text for the following signal categories. Look for direct mentions, paraphrases, and sentiment — not just keyword matches.

| Signal | Keywords / Patterns |
|--------|-------------------|
| **Churn intent** | cancel, leave, stop using, not renewing, switching away, looking for alternatives |
| **Budget pressure** | budget cut, cost reduction, freeze, can't afford, reducing spend, ROI concern |
| **Competitor evaluation** | looking at [competitor], evaluating [X], comparing options, demo with, talking to |
| **Implementation stall** | haven't set it up, still haven't launched, delayed, no one's using it, stuck on |
| **Dissatisfaction** | frustrated, disappointed, not what we expected, doesn't work for us, promised |
| **Escalation signals** | talked to legal, contract review, executive involved, urgent |

For each signal found, capture:
- The signal category
- A direct quote (20–60 words) as evidence
- Which call it came from (date + title if available)

### Step 4: Check Slack

Use the Slack MCP (`mcp__claude_ai_Slack__slack_search_public_and_private`) to search the `slack_channel` for each account name over the last `window_days` days.

Look for:
- Complaints or escalations from the CSM
- Red flags mentioned by internal team
- Positive signals (expansion, referral, praise) — these *reduce* risk score

Capture any relevant messages as quotes with author and date.

### Step 5: Score Each Account

Score each account **High / Medium / Low** using this rubric:

**High risk** — any of:
- Churn intent signal found in calls or Slack
- 2+ distinct signal categories in the last 30 days
- Escalation signal present
- No calls in last 30 days AND Slack shows concern

**Medium risk** — any of:
- 1 signal category found (budget, competitor, stall, or dissatisfaction)
- No calls found but account is large (top 10 by ARR)
- Slack mentions suggest friction but no hard churn language

**Low risk** — all of:
- No signals found
- Calls present and tone is neutral/positive
- No Slack red flags

### Step 6: Generate Recommended Actions

For each account, generate 3 specific next actions based on the signals found. Make them concrete and actionable, not generic. Examples:

- "Schedule an executive business review — last call showed implementation hasn't started"
- "Loop in AE to reframe ROI before Q2 budget review (mentioned in Apr 14 call)"
- "Send a competitive battle card to the CSM — [competitor] mentioned twice this month"
- "No risk signals found — good candidate for upsell or expansion conversation"

### Step 7: Write the Report

Save to a file named `account-risk-YYYY-MM-DD.md` (today's date) in the current working directory.

## Report Format

Use this exact structure:

```markdown
# Account Risk Report — YYYY-MM-DD
**Accounts scanned:** N | **Window:** X days | **Channel:** #channel-name

---

## 🔴 High Risk

### [Account Name] — $X,XXX ARR
**Risk:** High | **Owner:** [name] | **Last call:** [date or "None in window"]

**Risk Signals:**
1. [Signal category] — "[exact quote from call or Slack]" *(source: call title, date)*
2. [Signal category] — "[exact quote]" *(source)*
3. [Signal category] — "[exact quote]" *(source)*

**Recommended Actions:**
1. [Action]
2. [Action]
3. [Action]

---

[repeat for each high-risk account]

---

## 🟡 Medium Risk

[same format]

---

## 🟢 Low Risk

[same format — keep brief, one line of signals or "No risk signals found"]

---

## Summary
| Risk Level | Count | % of Accounts |
|------------|-------|---------------|
| 🔴 High    | X     | X%            |
| 🟡 Medium  | X     | X%            |
| 🟢 Low     | X     | X%            |

**Top 3 accounts needing immediate attention:**
1. [Account] — [one-line reason]
2. [Account] — [one-line reason]
3. [Account] — [one-line reason]
```

After saving the file, tell the user:
- The filename and path
- How many accounts were scanned
- The high/medium/low breakdown
- Top 3 accounts needing immediate attention

## Notes

- If HubSpot isn't available or returns no results, tell the user and stop — don't hallucinate account data.
- If Gong/Grain returns no transcripts for most accounts, note the coverage gap in the report header.
- Slack search may require the channel ID rather than name — try name first, then search for the channel ID using `slack_search_channels` if needed.
- When no signal is found, that's useful data too — say so clearly rather than inferring risk from nothing.
