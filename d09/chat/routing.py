from django.urls import path

from . import consumers

# Équivalent d'urls.py pour les websockets (utilisé dans d09/asgi.py).
# Le navigateur se connecte à ws://<hote>/ws/chat/<id de la room>/
websocket_urlpatterns = [
    path('ws/chat/<int:room_id>/', consumers.ChatConsumer.as_asgi()),
]
