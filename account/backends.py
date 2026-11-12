from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrCinBackend(ModelBackend):
    """Connexion avec (e-mail OU CIN) + mot de passe."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or kwargs.get('email') or '').strip()
        if not identifier or password is None:
            return None
        User = get_user_model()
        user = User.objects.filter(Q(email__iexact=identifier) | Q(cin=identifier)).first()
        if user is None:
            User().set_password(password)  # temps de calcul constant
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
