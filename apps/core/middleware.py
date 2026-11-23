from django.utils.cache import add_never_cache_headers


class NoCacheForAuthenticatedMiddleware:
    """
    Prevents browsers from serving cached authenticated views from the back-forward cache (bfcache)
    after a user logs out.
    Enforces strict Cache-Control, Pragma, and Expires headers.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Apply to authenticated sessions and protected URL paths
        is_auth = hasattr(request, 'user') and request.user.is_authenticated
        is_protected_path = request.path.startswith((
            '/dashboard/', '/sales/', '/production/', '/inventory/',
            '/finance/', '/master-data/', '/audit/', '/accounts/users/'
        ))

        if is_auth or is_protected_path:
            add_never_cache_headers(response)
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0, private'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response
