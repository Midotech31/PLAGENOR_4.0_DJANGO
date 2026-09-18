from django.test.client import closing_iterator_wrapper


def close_response(response):
    """Release response files using the Django test client's signal lifecycle."""
    if not response.closed:
        for _ in closing_iterator_wrapper((), response.close):
            pass
