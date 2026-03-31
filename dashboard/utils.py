from django.shortcuts import redirect
from django.urls import NoReverseMatch
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.exceptions import ValidationError

# Optional: python-magic for MIME type detection
try:
    import magic
    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False


def redirect_back(request, fallback_url='dashboard:router'):
    """Redirect to the referring page, preserving tab context."""
    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        return redirect(referer)
    try:
        return redirect(fallback_url)
    except NoReverseMatch:
        # URL pattern not found - redirect to home
        return redirect('/')


def paginate_queryset(queryset, request, per_page=25, page_param='page'):
    """
    Paginate a queryset and return (paginator, page, object_list).
    
    Args:
        queryset: The Django QuerySet to paginate
        request: The HTTP request (for GET parameters)
        per_page: Number of items per page (default: 25)
        page_param: Name of the page parameter in GET (default: 'page')
    
    Returns:
        Tuple of (paginator, page_obj, object_list)
    """
    paginator = Paginator(queryset, per_page)
    page = request.GET.get(page_param, 1)
    try:
        paginated = paginator.page(page)
    except PageNotAnInteger:
        paginated = paginator.page(1)
    except EmptyPage:
        paginated = paginator.page(paginator.num_pages)
    return paginator, paginated, paginated.object_list


# Allowed file types and their MIME types
ALLOWED_FILE_TYPES = {
    'pdf': ['application/pdf'],
    'fasta': ['text/plain', 'application/octet-stream'],
    'fastq': ['text/plain', 'application/octet-stream'],
    'csv': ['text/csv', 'text/plain', 'application/csv'],
    'image': ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
    'docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
    'xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
}

# File extensions by type
ALLOWED_EXTENSIONS = {
    'pdf': ['.pdf'],
    'fasta': ['.fasta', '.fa', '.fna'],
    'fastq': ['.fastq', '.fq'],
    'csv': ['.csv'],
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
    'docx': ['.docx'],
    'xlsx': ['.xlsx'],
}

# Max file size: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes


def validate_file_upload(file, allowed_types=None):
    """
    Validate an uploaded file for type and size.
    
    Args:
        file: UploadedFile object
        allowed_types: List of allowed type keys (e.g., ['pdf', 'fasta', 'image'])
                      If None, allows all known types.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if file is None:
        return False, "No file provided"
    
    # Check file size
    if file.size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        return False, f"File size exceeds maximum allowed ({max_mb:.0f}MB)"
    
    # Check file extension
    filename = file.name.lower()
    allowed_extensions = set()
    if allowed_types:
        for type_key in allowed_types:
            if type_key in ALLOWED_EXTENSIONS:
                allowed_extensions.update(ALLOWED_EXTENSIONS[type_key])
    else:
        for exts in ALLOWED_EXTENSIONS.values():
            allowed_extensions.update(exts)
    
    has_valid_extension = any(filename.endswith(ext) for ext in allowed_extensions)
    
    # Also validate MIME type using python-magic if available
    if HAS_MAGIC:
        try:
            file.seek(0)
            mime_type = magic.from_buffer(file.read(2048), mime=True)
            file.seek(0)
            
            # Check MIME type against allowed types
            mime_allowed = False
            if allowed_types:
                for type_key in allowed_types:
                    if type_key in ALLOWED_FILE_TYPES:
                        if mime_type in ALLOWED_FILE_TYPES[type_key]:
                            mime_allowed = True
                            break
            else:
                for types in ALLOWED_FILE_TYPES.values():
                    if mime_type in types:
                        mime_allowed = True
                        break
            
            if not mime_allowed and not has_valid_extension:
                return False, f"File type not allowed. Allowed types: {', '.join(sorted(allowed_extensions))}"
        except Exception:
            # If magic can't determine type, rely on extension
            if not has_valid_extension:
                return False, f"File extension not allowed. Allowed extensions: {', '.join(sorted(allowed_extensions))}"
    else:
        # Without magic, rely on extension only
        if not has_valid_extension:
            return False, f"File extension not allowed. Allowed extensions: {', '.join(sorted(allowed_extensions))}"
    
    return True, None


def get_allowed_extensions_display():
    """Get a human-readable list of allowed file extensions."""
    all_extensions = []
    for exts in ALLOWED_EXTENSIONS.values():
        all_extensions.extend(exts)
    return ', '.join(sorted(set(all_extensions)))
