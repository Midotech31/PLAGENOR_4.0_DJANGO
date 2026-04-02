# Fix: Remove Duplicate Form Fields - Only Show in Sample Table

## Problem
The IBTIKAR request form was showing duplicate fields:
- Fields appeared as separate static form fields above the table  
- Same fields also appeared as columns in the sample table

The issue was that `ServiceFormField` records with `field_category='sample_table'` were being loaded as `db_fields` and rendered as separate form fields, even though they should only appear as table columns.

Affected fields:
- Cultures fraîches
- Cible MALDI
- Mode analyse
- N°
- Code
- Type microorganisme
- Source isolement
- Date isolement
- Milieu culture
- Conditions culture
- Remarques

## Root Cause
In `dashboard/views/service_form_api.py`, the query loaded ALL form fields:
```python
db_fields = list(svc.form_fields.all().values(...))
```

This included both `sample_table` and `additional_info` fields. The template tried to filter them by comparing names against YAML column names, but the DB field names (e.g., `id`, `code`, `organism`) didn't match the YAML column names (e.g., `sample_code`, `organism_type`), so the filtering failed.

## Solution
Filter the DB query to only load `additional_info` fields:

### 1. dashboard/views/service_form_api.py (line 31)
Changed:
```python
db_fields = list(svc.form_fields.all().values('name', 'label', 'field_type', 'options', 'required'))
```

To:
```python
db_fields = list(svc.form_fields.filter(field_category='additional_info').values('name', 'label', 'field_type', 'options', 'required'))
```

### 2. templates/includes/service_form_fields.html
Simplified the db_fields loop by removing the redundant check (since we now filter at the query level).

## Result
Only `additional_info` fields now appear as separate form fields. All `sample_table` fields only appear as columns in the sample table.
