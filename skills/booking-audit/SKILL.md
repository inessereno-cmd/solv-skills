---
name: booking-audit
description: Query and audit booking data including status changes, clinic author information, and booking history. Use when users ask about who changed a booking status, booking timelines, staff actions on bookings, or general booking data analysis using dim_bookings and dim_clinic_accounts tables.
---

# Booking Audit and Query Skill

## When to Use This Skill

Use this skill when users ask questions about:
- Finding who changed a booking to a specific status (discharged, checked in, cancelled, etc.)
- Auditing booking status changes and timelines
- Looking up clinic staff/author information for booking actions
- Querying booking history and changes over time
- General booking data analysis and investigation

## Key Principles

1. **Primary booking identifier is `id_hash`** - NOT `booking_id_hash`
2. **Never use the `booking_changes` table** - It's not relevant for most audit questions
3. **Always join to `dim_clinic_accounts`** to get full names of clinic authors
4. **Use `stg_postgres_table_history`** for complete historical audit trails

## Core Data Models

### dim_bookings
- Main source of truth for booking data
- Contains all status timestamps and author IDs
- Key column: `id_hash` (the booking identifier like 'RBJ5MK')
- Author ID columns: `discharged_author_id`, `checked_in_author_id`, `cancelled_author_id`, etc.

### dim_clinic_accounts  
- Clinic staff/user information
- Key column: `clinic_account_id`
- Contains: `first_name`, `last_name`, `email`, `role`
- Note: No `full_name` column - must concatenate `first_name || ' ' || last_name`

### stg_postgres_table_history
- Historical change tracking for all tables
- Query with: `WHERE table_name = 'bookings'`
- Use `row_id` (numeric booking id, not id_hash)

## Standard Query Pattern

When answering "Who changed booking X to status Y?":
```sql
-- Step 1: Get the booking and author_id
SELECT 
  b.id_hash,
  b.status,
  b.{status}_timestamp,
  b.{status}_author_id
FROM {{ ref('dim_bookings') }} b
WHERE b.id_hash = '<BOOKING_HASH>'
LIMIT 1

-- Step 2: Look up the author details
SELECT 
  clinic_account_id,
  first_name || ' ' || last_name as full_name,
  email,
  role
FROM {{ ref('dim_clinic_accounts') }}
WHERE clinic_account_id = <AUTHOR_ID>
```

Or as a single joined query:
```sql
SELECT 
  b.id_hash,
  b.status,
  b.{status}_timestamp,
  ca.first_name || ' ' || ca.last_name as author_full_name,
  ca.role,
  ca.email
FROM {{ ref('dim_bookings') }} b
LEFT JOIN {{ ref('dim_clinic_accounts') }} ca 
  ON b.{status}_author_id = ca.clinic_account_id
WHERE b.id_hash = '<BOOKING_HASH>'
```

## Common Status Author Columns

Replace `{status}` with:
- `discharged` - For discharge actions
- `checked_in` - For check-in actions  
- `cancelled` - For cancellation actions
- `created` - For booking creation
- `confirmed` - For confirmation actions
- `arrived` - For arrival actions
- `in_exam_room` - For when moved to exam room

## Querying Booking History

To see all historical changes to a booking:
```sql
-- First, get the numeric booking id
SELECT id, id_hash 
FROM {{ ref('dim_bookings') }} 
WHERE id_hash = '<BOOKING_HASH>'

-- Then query the history table
SELECT *
FROM {{ ref('stg_postgres_table_history') }}
WHERE table_name = 'bookings'
  AND row_id = '<NUMERIC_ID_FROM_ABOVE>'
ORDER BY updated_at DESC
```

## Common Pitfalls to Avoid

1. ❌ Using `booking_id_hash` → ✅ Use `id_hash`
2. ❌ Querying `booking_changes` table → ✅ Use `dim_bookings` 
3. ❌ Selecting `full_name` from clinic_accounts → ✅ Concatenate `first_name || ' ' || last_name`
4. ❌ Using `id` column → ✅ Use `clinic_account_id`
5. ❌ Direct table names → ✅ Use `{{ ref('model_name') }}`

## Workflow for Booking Questions

1. **Identify the booking** - Use id_hash in dim_bookings
2. **Check current state** - SELECT the booking to see available data
3. **Determine status of interest** - Which status change are we investigating?
4. **Get author_id** - Look for `{status}_author_id` column
5. **Join to get name** - Join to dim_clinic_accounts on clinic_account_id
6. **Return full answer** - Include full name, role, timestamp, and any other context

## Example Queries

### Who discharged a booking?
```sql
SELECT 
  ca.first_name || ' ' || ca.last_name as full_name,
  ca.role,
  b.discharged_timestamp as when_discharged
FROM {{ ref('dim_bookings') }} b
JOIN {{ ref('dim_clinic_accounts') }} ca 
  ON b.discharged_author_id = ca.clinic_account_id
WHERE b.id_hash = 'RBJ5MK'
```

### Complete status timeline
```sql
SELECT 
  id_hash,
  status,
  created_date,
  arrived_timestamp,
  checked_in_timestamp,
  in_exam_room_timestamp,
  discharged_timestamp,
  cancellation_timestamp
FROM {{ ref('dim_bookings') }}
WHERE id_hash = 'ABC123'
```

### All bookings by a specific clinic user
```sql
SELECT 
  b.id_hash,
  b.discharged_timestamp,
  b.status
FROM {{ ref('dim_bookings') }} b
WHERE b.discharged_author_id = 91009
  AND b.discharged_timestamp IS NOT NULL
ORDER BY b.discharged_timestamp DESC
LIMIT 20
```

## Performance Tips

- Always use `LIMIT` when exploring data
- Start with `LIMIT 1` to verify query works before expanding
- Select only needed columns, avoid `SELECT *` on large tables
- Use specific WHERE clauses to filter to relevant bookings

## Output Format

When answering booking audit questions, provide:
1. **Direct answer** - The full name of the person who made the change
2. **Context** - Their role, the timestamp, and any relevant details
3. **Supporting data** - Other relevant booking information if requested

Example response format:
"The booking RBJ5MK was discharged by **Brenda Chavez** (provider) on September 19, 2025 at 11:35 AM local time."