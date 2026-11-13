from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            matches = list(User.objects.filter(email__iexact=username)[:2])
            if len(matches) != 1:
                User().set_password(password)
                return None
            user = matches[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
