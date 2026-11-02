from django.contrib.auth.forms import UserCreationForm

from .models import CustomUser


class SignUpForm(UserCreationForm):
    """Formulaire de création d'utilisateur.

    UserCreationForm est lié par défaut au modèle auth.User ; comme le projet
    utilise AUTH_USER_MODEL = account.CustomUser, on pointe Meta.model dessus.
    Il fournit gratuitement : nom unique, mot de passe + confirmation, et les
    validateurs de AUTH_PASSWORD_VALIDATORS (longueur, mots de passe courants...).
    """

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('username',)
