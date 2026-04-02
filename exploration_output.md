# PLAGENOR 4.0 Django Codebase Exploration Results

## 1. documents/urls.py - URL Patterns

**Path:** `C:\Users\hp\OneDrive\PLAGENOR_4.0_DJANGO\documents\urls.py`

```python
urlpatterns = [
    path('ibtikar-form/<int:pk>/', views.download_ibtikar_form, name='ibtikar_form'),
    path('platform-note/<int:pk>/', views.download_platform_note, name='platform_note'),
    path('reception-form/<int:pk>/', views.download_reception_form, name='reception_form'),
    path('regenerate/<int:pk>/<str:doc_type>/', views.regenerate_pdf, name='regenerate_pdf'),
    path('ibtikar/<int:request_id>/', views.ibtikar_form_view, name='ibtikar_form_legacy'),
    path('platform_note/<int:request_id>/', views.platform_note_view, name='platform_note_legacy'),
    path('reception/<int:request_id>/', views.reception_form_view, name='reception_form_legacy'),
    path('status/<int:pk>/', views.check_pdf_status, name='pdf_status'),
]
```

**Issue:** URLs use `<int:pk>/` but Request model uses UUID primary keys.

---

## 2. templates/dashboard/requester/index.html (Line 153)

**Path:** `C:\Users\hp\OneDrive\PLAGENOR_4.0_DJANGO\templates\dashboard\requester\index.html`

```html
{% if req.channel == 'IBTIKAR' %}
{% if req.status == 'IBTIKAR_SUBMISSION_PENDING' or req.status == 'IBTIKAR_CODE_SUBMITTED' %}
{% url 'documents:ibtikar_form' req.pk as ibkformurl %}
{% url 'dashboard:requester_ibtikar_code' req.pk as ibkcodeurl %}
{% include 'includes/ibtikar_submission_workflow.html' with ibk_req=req ibk_form_url=ibkformurl ibk_code_submit_url=ibkcodeurl %}
{% else %}
<div class="data-card-row mt-1" style="gap: 0.5rem;">
    <a href="{% url 'documents:ibtikar_form' req.pk %}" class="btn btn-sm btn-outline">{% trans "Formulaire IBTIKAR" %}</a>
</div>
{% endif %}
{% endif %}
```

---

## 3. EGTP-IMT Docx Template Files

**Finding:** NO .docx template files exist. Documents are generated programmatically using ReportLab/Python.

### References to EGTP-IMT:

**a) documents/pdf_generator_ibtikar.py (Line 351):**
```python
service_display_names = {
    'EGTP-IMT': 'DEMANDE D\'IDENTIFICATION PAR MALDI-TOF',
    ...
}
```

**b) core/migrations/0019_populate_service_form_fields.py (Lines 406-458):**
```python
'EGTP-IMT': {
    'sample_table': [
        {'name': 'id', 'label': 'N°', ...},
        {'name': 'code', 'label': 'Code', ...},
        {'name': 'organism', 'label': 'Type microorganisme', ...},
        {'name': 'isolation', 'label': 'Source isolement', ...},
        {'name': 'isolation_date', 'label': 'Date isolement', ...},
        {'name': 'culture_medium', 'label': 'Milieu culture', ...},
        {'name': 'culture_conditions', 'label': 'Conditions culture', ...},
        {'name': 'notes', 'label': 'Remarques', ...},
    ],
    'additional_info': [...],
    ...
}
```

---

## 4. Request Model - UUIDField as Primary Key

**Path:** `C:\Users\hp\OneDrive\PLAGENOR_4.0_DJANGO\core\models.py` (Line 292)

```python
class Request(models.Model):
    CHANNEL_CHOICES = [
        ('IBTIKAR', 'IBTIKAR'),
        ('GENOCLAB', 'GENOCLAB'),
    ]

    URGENCY_CHOICES = [
        ('Normal', 'Normal'),
        ('Urgent', 'Urgent'),
        ('Très urgent', 'Très urgent'),
    ]

    STATUS_CHOICES = [
        ('DRAFT', 'Brouillon'),
        ('SUBMITTED', 'Soumis'),
        # ... many more statuses
    ]

    # PRIMARY KEY: UUIDField
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_id = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=300)
    # ... rest of model
```

**CONFIRMED:** Request model uses UUIDField as primary key.

---

## 5. Views That Handle Request PK

### 5.1 dashboard/urls.py - All request URLs (Use `<uuid:pk>`):

```python
path('home/request/<uuid:pk>/detail/', superadmin.request_detail, name='superadmin_request_detail'),
path('ops/request/<uuid:pk>/', admin_ops.request_detail, name='admin_request_detail'),
path('analyst/request/<uuid:pk>/', analyst.request_detail, name='analyst_request_detail'),
path('requester/request/<uuid:pk>/', requester.request_detail, name='requester_request_detail'),
path('client/request/<uuid:pk>/', client.request_detail, name='client_request_detail'),
```

### 5.2 documents/urls.py - PROBLEM: Uses `<int:pk>`:

```python
path('ibtikar-form/<int:pk>/', views.download_ibtikar_form, name='ibtikar_form'),
path('platform-note/<int:pk>/', views.download_platform_note, name='platform_note'),
path('reception-form/<int:pk>/', views.download_reception_form, name='reception_form'),
```

### 5.3 Sample View: dashboard/views/requester.py (Line 104):

```python
@requester_required
def request_detail(request, pk):
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    # ...
```

### 5.4 Sample View: documents/views.py (Line 26):

```python
@login_required
def download_ibtikar_form(request, pk):
    req = get_object_or_404(Request, pk=pk)
    # ...
```

---

## Summary

| Item | Status | Notes |
|------|--------|-------|
| documents/urls.py | **BUG** | Uses `<int:pk>` but Request uses UUID PK - will cause 404 errors |
| templates/dashboard/requester/index.html | OK | Uses `req.pk` which Django handles |
| EGTP-IMT docx templates | Not Found | Documents generated programmatically via ReportLab |
| Request model PK | **UUIDField** | `id = models.UUIDField(primary_key=True, default=uuid.uuid4)` |
| Dashboard URLs | Correct | All use `<uuid:pk>` for Request views |

---

## File Paths Summary

1. **documents/urls.py:** `C:\Users\hp\OneDrive\PLAGENOR_4.0_DJANGO\documents\urls.py`
2. **requester/index.html:** `C:\Users\hp\OneDrive\PLAGENOR_4.0_DJANGO\templates\dashboard\requester\index.html`
3. **EGTP-IMT references:** 
   - `C:\Users\hp\OneDrive\PLAGENOR_4.0_DJANGO\documents\pdf_generator_ibtikar.py` (line 351)
   - `C:\Users\hp\OneDrive\PLAGENOR_4.0_DJANGO\core\migrations\0019_populate_service_form_fields.py` (lines 406-458)
4. **Request model:** `C:\Users\hp\OneDrive\PLAGENOR_4.0_DJANGO\core\models.py` (line 245)
5. **documents/views.py:** `C:\Users\hp\OneDrive\PLAGENOR_4.0_DJANGO\documents\views.py`
6. **dashboard/urls.py:** `C:\Users\hp\OneDrive\PLAGENOR_4.0_DJANGO\dashboard\urls.py`
7. **dashboard/views/requester.py:** `C:\Users\hp\OneDrive\PLAGENOR_4.0_DJANGO\dashboard\views\requester.py`
