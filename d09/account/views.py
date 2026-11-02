# Ex00 – vues AJAX de connexion / déconnexion.
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .forms import SignUpForm


def _auth_forms():
    """Les deux formulaires du fragment _login_form.html : connexion et inscription.
    auto_id='register_%s' évite des ids HTML en double (id_username) entre les deux."""
    return {'form': AuthenticationForm(),
            'register_form': SignUpForm(auto_id='register_%s')}


# Page /account/ : affiche le formulaire ou "Logged as ..." selon l'état de
# connexion (voir account.html). ensure_csrf_cookie force l'envoi du cookie
# csrftoken, dont le JavaScript a besoin pour ses requêtes POST.
@ensure_csrf_cookie
def account_view(request):
    return render(request, 'account/account.html', _auth_forms())


# Appelée en AJAX (POST uniquement). Renvoie du JSON, jamais une page entière :
# - formulaire valide   -> l'utilisateur est connecté, on renvoie le HTML
#   "Logged as ..." que le JS insère dans la page ;
# - formulaire invalide -> HTTP 400 + dictionnaire d'erreurs pour l'affichage.
@require_POST
def login_view(request):
    form = AuthenticationForm(request, data=request.POST)
    if form.is_valid():
        login(request, form.get_user())
        html = render_to_string('account/_logged_in.html', request=request)
        return JsonResponse({'html': html})
    return JsonResponse({'errors': form.errors}, status=400)


# Appelée en AJAX (POST uniquement) : déconnecte puis renvoie le HTML du
# formulaire de login pour que la page change sans rechargement.
@require_POST
def logout_view(request):
    logout(request)
    html = render_to_string('account/_login_form.html', _auth_forms(),
                            request=request)
    return JsonResponse({'html': html})


# Création d'un utilisateur, en AJAX (POST uniquement) comme le login.
# Si le formulaire est valide, l'utilisateur est créé ET connecté directement
# (plus simple pour lui), puis on renvoie le HTML "Logged as ...".
# Sinon : HTTP 400 + erreurs (nom déjà pris, mots de passe différents/trop faibles...).
@require_POST
def register_view(request):
    form = SignUpForm(request.POST)
    if form.is_valid():
        user = form.save()
        login(request, user)
        html = render_to_string('account/_logged_in.html', request=request)
        return JsonResponse({'html': html})
    return JsonResponse({'errors': form.errors}, status=400)
