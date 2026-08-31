# Playbook — Business Data Analysis

## Intake

Preserve the original file and record filename, byte size, hash, sheet/table names, row count and date range.

## Data dictionary

For every field record:

| Field | Meaning | Type | Unit | Allowed values | Missing meaning | Source owner |
|---|---|---|---|---|---|---|

Do not infer business meaning from a short column name when an owner can clarify it.

## Quality profile

Check:

- unique key and duplicates;
- missing values;
- invalid dates;
- text stored as numbers or vice versa;
- category spelling and whitespace;
- negative or impossible quantities;
- currency and tax basis;
- formula errors;
- outliers requiring business explanation.

## Cleaning log

Every change records rule, affected rows, before/after values, reason and whether the source was changed or a cleaned copy was created.

## Metric definitions

For each KPI specify formula, filters, unit, period, treatment of refunds/discounts/tax and reconciliation target.

## Analysis sequence

1. Scope and totals.
2. Distribution and concentration.
3. Time trend.
4. Region, channel, category and salesperson.
5. Cross-dimension combinations.
6. Change and exception analysis.
7. Business explanation and missing evidence.

## Reconciliation

Compare:

- source row count versus cleaned row count;
- source total versus cleaned total;
- dashboard KPI versus independent calculation;
- representative records versus grouped result.

## Dashboard rule

Every visual answers a written business question. Remove a chart if no decision changes after seeing it.

## Delivery

- source manifest;
- cleaned data;
- cleaning log;
- data dictionary;
- metric definitions;
- findings;
- dashboard;
- reconciliation evidence;
- decisions and risks.
