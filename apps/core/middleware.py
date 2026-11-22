from django.utils.cache import add_never_cache_headers


class NoCacheForAuthenticatedMiddleware:
    """
    Prevents browsers from serving cached authenticated views from the back-forward cache (bfcache)
    after a user logs out.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if hasattr(request, 'user') and request.user.is_authenticated:
            add_never_cache_headers(response)
        return response
