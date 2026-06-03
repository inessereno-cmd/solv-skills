---
skillName: Maya Voice Agent Call Analysis
description: Analyze Maya voice agent call subjects by group or location using dbt data warehouse
version: 1.0.0
author: Analytics Team
tags:
  - maya
  - voice-agent
  - call-analysis
  - healthcare
  - dbt
---

# Maya Voice Agent Call Subject Analysis

## Overview
This skills file provides instructions for analyzing Maya voice agent call subjects by group or location using the dbt data warehouse.

## Available Data Models
- **fact_voice_agent_calls**: Main fact table containing voice agent call data
- **dim_locations**: Location dimension with names and addresses
- **dim_groups**: Group/organization dimension
- **stg_postgres_groups**: Staging table for group information

## Key Fields
- `call_subjects`: Comma-separated list of call subjects for each call
- `primary_call_subject`: The primary subject identified for the call
- `call_start_date`: Timestamp when the call started
- `location_id`: Foreign key to location
- `group_id`: Foreign key to group/organization

## Standard Analysis Queries

### 1. Find a Group by Name
```sql
SELECT DISTINCT name, id, parent_group_id
FROM stg_postgres_groups 
WHERE name ILIKE '%[GROUP_NAME]%'
LIMIT 10
```

### 2. Get Locations for a Group
```sql
SELECT 
    l.id as location_id,
    l.name as location_name,
    l.city,
    l.state
FROM dim_locations l
WHERE l.group_id = [GROUP_ID]
ORDER BY l.name
```

### 3. Get Date Range of Available Data
```sql
SELECT 
    MIN(call_start_date) as earliest_call_date,
    MAX(call_start_date) as latest_call_date,
    COUNT(*) as total_calls
FROM fact_voice_agent_calls
WHERE group_id = [GROUP_ID]
```

### 4. Get Top N Call Subjects by Location
```sql
WITH call_subjects_unnested AS (
    SELECT 
        l.name as location_name,
        vac.location_id,
        TRIM(SPLIT_PART(vac.call_subjects, ',', numbers.n)) as call_subject,
        COUNT(*) as call_count
    FROM fact_voice_agent_calls vac
    INNER JOIN dim_locations l ON vac.location_id = l.id
    CROSS JOIN (
        SELECT 1 as n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL 
        SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL 
        SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9 UNION ALL SELECT 10
    ) numbers
    WHERE vac.group_id = [GROUP_ID]
        AND vac.call_subjects IS NOT NULL
        AND vac.call_subjects != ''
        AND vac.call_subjects != 'Not Available'
        AND SPLIT_PART(vac.call_subjects, ',', numbers.n) != ''
    GROUP BY 1, 2, 3
),
ranked_subjects AS (
    SELECT 
        location_name,
        location_id,
        call_subject,
        call_count,
        ROW_NUMBER() OVER (PARTITION BY location_id ORDER BY call_count DESC) as rank
    FROM call_subjects_unnested
)
SELECT 
    location_name,
    call_subject,
    call_count,
    rank
FROM ranked_subjects
WHERE rank <= [TOP_N]
ORDER BY location_name, rank
```

### 5. Get Top Call Subjects Across All Locations (Aggregated)
```sql
WITH call_subjects_unnested AS (
    SELECT 
        TRIM(SPLIT_PART(vac.call_subjects, ',', numbers.n)) as call_subject,
        COUNT(*) as call_count
    FROM fact_voice_agent_calls vac
    CROSS JOIN (
        SELECT 1 as n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL 
        SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL 
        SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9 UNION ALL SELECT 10
    ) numbers
    WHERE vac.group_id = [GROUP_ID]
        AND vac.call_subjects IS NOT NULL
        AND vac.call_subjects != ''
        AND vac.call_subjects != 'Not Available'
        AND SPLIT_PART(vac.call_subjects, ',', numbers.n) != ''
    GROUP BY 1
)
SELECT 
    call_subject,
    call_count,
    ROW_NUMBER() OVER (ORDER BY call_count DESC) as rank
FROM call_subjects_unnested
ORDER BY call_count DESC
LIMIT [TOP_N]
```

### 6. Filter by Date Range
Add this WHERE clause to any query:
```sql
WHERE vac.call_start_date >= '[START_DATE]'
  AND vac.call_start_date < '[END_DATE]'
  AND vac.group_id = [GROUP_ID]
```

### 7. Get Call Volume by Location
```sql
SELECT 
    l.name as location_name,
    COUNT(*) as total_calls,
    COUNT(CASE WHEN vac.call_subjects LIKE '%Transfer to representative%' THEN 1 END) as transfer_calls,
    ROUND(100.0 * COUNT(CASE WHEN vac.call_subjects LIKE '%Transfer to representative%' THEN 1 END) / COUNT(*), 2) as transfer_percentage
FROM fact_voice_agent_calls vac
INNER JOIN dim_locations l ON vac.location_id = l.id
WHERE vac.group_id = [GROUP_ID]
GROUP BY l.name
ORDER BY total_calls DESC
```

## Usage Instructions

### To Analyze a New Group:

1. **Find the Group ID**
   - Replace `[GROUP_NAME]` with the organization name
   - Run Query #1

2. **Get Location Context**
   - Replace `[GROUP_ID]` with the ID from step 1
   - Run Query #2 to see all locations

3. **Check Data Availability**
   - Run Query #3 to understand the date range

4. **Analyze Top Call Subjects**
   - For top 5 by location: Use Query #4 with `[TOP_N] = 5`
   - For top 20 by location: Use Query #4 with `[TOP_N] = 20`
   - For overall top subjects: Use Query #5

5. **Create Visualizations**
   - Use Query #5 results to create bar charts
   - Show total counts, percentages, or rankings

## Example: Little Spurs Analysis

```sql
-- Step 1: Find group
SELECT DISTINCT name, id FROM stg_postgres_groups 
WHERE name ILIKE '%little spurs%'
-- Result: Little Spurs Pediatric Urgent Care, ID: 280

-- Step 2: Get date range
SELECT 
    MIN(call_start_date) as earliest_call_date,
    MAX(call_start_date) as latest_call_date,
    COUNT(*) as total_calls
FROM fact_voice_agent_calls
WHERE group_id = 280
-- Result: June 30, 2025 - Nov 24, 2025, 55,200 calls

-- Step 3: Get top 5 subjects by location
-- (Use Query #4 with TOP_N = 5)
```

## Key Metrics to Report

1. **Date range** of data analyzed
2. **Total calls** in the period
3. **Number of locations** analyzed
4. **Top N call subjects** (usually 5-20)
5. **Transfer rate** (percentage of calls transferred to representative)
6. **Geographic insights** (if applicable)

## Tips for Analysis

- Always start by identifying the group ID
- Check the date range to set proper context
- The `call_subjects` field can contain multiple subjects (comma-separated)
- "Transfer to representative" is often the #1 subject - this indicates handoff frequency
- Compare across locations to identify outliers or best practices
- Consider filtering by date ranges for trending analysis

## Common Variations

### Monthly Trends
```sql
SELECT 
    DATE_TRUNC('month', call_start_date) as month,
    COUNT(*) as total_calls
FROM fact_voice_agent_calls
WHERE group_id = [GROUP_ID]
GROUP BY DATE_TRUNC('month', call_start_date)
ORDER BY month
```

### Day of Week Analysis
```sql
SELECT 
    TO_CHAR(call_start_date, 'Day') as day_of_week,
    COUNT(*) as total_calls
FROM fact_voice_agent_calls
WHERE group_id = [GROUP_ID]
GROUP BY TO_CHAR(call_start_date, 'Day')
ORDER BY total_calls DESC
```

### Hour of Day Analysis
```sql
SELECT 
    EXTRACT(HOUR FROM call_start_date) as hour_of_day,
    COUNT(*) as total_calls
FROM fact_voice_agent_calls
WHERE group_id = [GROUP_ID]
GROUP BY EXTRACT(HOUR FROM call_start_date)
ORDER BY hour_of_day
```

---

## Quick Reference Card

| What You Want | Query to Use |
|---------------|--------------|
| Find a group | Query #1 |
| List locations | Query #2 |
| Check data availability | Query #3 |
| Top subjects by location | Query #4 |
| Overall top subjects | Query #5 |
| Filter by date | Query #6 addition |
| Call volume stats | Query #7 |

Remember: Always replace `[GROUP_ID]`, `[GROUP_NAME]`, `[TOP_N]`, `[START_DATE]`, and `[END_DATE]` with actual values!