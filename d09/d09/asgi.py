"""
ASGI config for d09 project.

HTTP requests go to Django, websocket connections go to the chat consumers.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'd09.settings')

# Must be called before importing anything that touches the ORM / models.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

import chat.routing  # noqa: E402

# Aiguillage selon le protocole :
#  - http      -> application Django habituelle ;
#  - websocket -> vérification de l'origine (ALLOWED_HOSTS), puis authentification
#                 via la session Django (donne scope['user']), puis routing du chat.
application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(URLRouter(chat.routing.websocket_urlpatterns))
    ),
})
