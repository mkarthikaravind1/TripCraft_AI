from .services import errors


def assistant(request):
    """Data the floating assistant widget needs on every page."""
    return {"assistant_error_codes": errors.all_codes()}
