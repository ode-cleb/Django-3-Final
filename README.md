# Django Final – d09

Un seul projet Django (`d09/`) : AJAX (ex00) puis chat Websocket (ex01 → ex04).
Seule librairie JS : jQuery (Bootstrap CSS autorisé par le sujet).

## Lancement
```bash
python -m venv venv && . venv/bin/activate
pip install -r requirement.txt
cd d09
python manage.py migrate        # crée aussi les 3 chatrooms par défaut
python manage.py createsuperuser
python manage.py runserver      # Daphne (ASGI) sert HTTP + websockets
```

* `/account/` : login / logout en AJAX (ex00) ; le bouton « Create user » permet de créer un compte (et de s'y connecter) sans quitter la page
* `/chat/` : liste des 3 chatrooms ; `/chat/<id>/` : le chat (ex01–ex04)
* `/admin/` : admin Django par défaut

Un rafraîchissement de page (F5) dans une room est transparent : pas de « left » ni de nouveau « joined », et la conversation est conservée. Le serveur suit la présence par onglet (identifiant `sid` conservé dans `sessionStorage`), ce qui marche quel que soit l'ordre ancien/nouveau websocket (voir `chat/consumers.py` et `chat/static/chat/js/chat.js`). Un vrai départ est annoncé après un court délai de grâce (`LEAVE_GRACE_SECONDS`, 3 s).

Le channel layer est `InMemoryChannelLayer` (pas de Redis) : à utiliser avec un seul process.

## Tests
```bash
cd d09 && python manage.py test
```
