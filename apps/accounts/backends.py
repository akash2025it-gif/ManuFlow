from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """
    Authenticate against CustomUser using either email or username.
    Prevents shared demo passwords from being used in production.
    """
    DEMO_PASSWORDS = {'nit@12345', 'TestPassword123!'}

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)

        if not username or not password:
            return None

        # Production Security Guard:
        # In production (when DEBUG=False and DEMO_MODE=False), strictly prohibit authentication
        # using well-known shared demo passwords.
        is_demo_mode = getattr(settings, 'DEMO_MODE', settings.DEBUG)
        if not is_demo_mode and password in self.DEMO_PASSWORDS:
            return None

        try:
            # Query by either email or username (case-insensitive)
            user = UserModel.objects.filter(
                Q(email__iexact=username) | Q(username__iexact=username)
            ).first()
        except UserModel.DoesNotExist:
            return None

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
