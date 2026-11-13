from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import ValidationError

from .validators import institutional_email


class InstitutionalEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        User = get_user_model()
        try:
            email = institutional_email(username)
        except ValidationError:
            User().set_password(password)
            return None
        matches = list(User.objects.filter(email__iexact=email)[:2])
        if len(matches) != 1:
            User().set_password(password)
            return None
        user = matches[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
