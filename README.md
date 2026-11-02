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

* `/account/` : login / logout en AJAX (ex00)
* `/chat/` : liste des 3 chatrooms ; `/chat/<id>/` : le chat (ex01–ex04)
* `/admin/` : admin Django par défaut

Le channel layer est `InMemoryChannelLayer` (pas de Redis) : à utiliser avec un seul process.

## Tests
```bash
cd d09 && python manage.py test
```
