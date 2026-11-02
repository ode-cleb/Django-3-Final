"""Consumer websocket du chat (ex01 à ex03).

Un *consumer* est l'équivalent d'une vue pour les websockets : une instance de
ChatConsumer est créée pour CHAQUE connexion navigateur. Les utilisateurs d'une
même room sont regroupés dans un "groupe" Channels : un group_send() envoie un
évènement à toutes les connexions du groupe (c'est ce qui permet à un message de
parvenir à tout le monde).

Messages JSON envoyés au navigateur (champ "type") :
  - history : les derniers messages de la room (ex02)
  - message : un message d'utilisateur
  - system  : "<user> has joined/left the chat"
  - users   : la liste des utilisateurs connectés (ex03)
"""
import json
from collections import defaultdict

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Chatroom, Message

# Nombre de messages envoyés à un nouvel arrivant (ex02).
HISTORY_SIZE = 3

# Suivi des utilisateurs connectés (ex03) : {room_id: {username: nb_connexions}}.
# On compte les connexions car un même utilisateur peut ouvrir plusieurs onglets :
# il ne disparaît de la liste que lorsque son DERNIER onglet est fermé.
# Un simple dict en mémoire suffit car le channel layer est lui aussi en mémoire
# (un seul processus serveur).
ONLINE = defaultdict(dict)


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Appelée à l'ouverture du websocket."""
        self.user = self.scope['user']  # fourni par AuthMiddlewareStack (session Django)
        self.room_id = self.scope['url_route']['kwargs']['room_id']  # vient de routing.py
        self.group = f'chat_{self.room_id}'  # nom du groupe Channels de cette room
        self.joined = False  # permet à disconnect() de savoir si la connexion a été acceptée

        # Chat réservé aux utilisateurs connectés, et la room doit exister.
        if not self.user.is_authenticated or not await self.room_exists():
            await self.close()
            return

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        self.joined = True

        # Ex03 : on enregistre l'utilisateur comme connecté dans cette room.
        users = ONLINE[self.room_id]
        users[self.user.username] = users.get(self.user.username, 0) + 1

        # Ex02 : historique, envoyé uniquement au nouvel arrivant (send = vers
        # cette connexion seule), du plus ancien au plus récent.
        await self.send(json.dumps({
            'type': 'history',
            'messages': await self.last_messages(),
        }))
        # Ex01 : "<user> has joined the chat" pour tout le groupe, y compris
        # l'arrivant lui-même (il est déjà membre du groupe).
        await self.channel_layer.group_send(self.group, {
            'type': 'chat.system',  # appelle la méthode chat_system ci-dessous
            'message': f'{self.user.username} has joined the chat',
        })
        # Ex03 : nouvelle liste d'utilisateurs pour tout le monde.
        await self.broadcast_users()

    async def disconnect(self, code):
        """Appelée quand le websocket se ferme (onglet fermé, déconnexion réseau...)."""
        if not getattr(self, 'joined', False):
            return  # connexion refusée au départ : rien à nettoyer

        # Ex03 : on décrémente le compteur, et on retire l'utilisateur de la
        # liste seulement s'il n'a plus aucun onglet ouvert.
        users = ONLINE[self.room_id]
        users[self.user.username] -= 1
        if users[self.user.username] <= 0:
            del users[self.user.username]
        if not users:
            ONLINE.pop(self.room_id, None)

        await self.channel_layer.group_discard(self.group, self.channel_name)
        # Ex03 : message "has left" puis liste mise à jour pour ceux qui restent.
        await self.channel_layer.group_send(self.group, {
            'type': 'chat.system',
            'message': f'{self.user.username} has left the chat',
        })
        await self.broadcast_users()

    async def receive(self, text_data=None, bytes_data=None):
        """Appelée quand le navigateur envoie un message : {"message": "..."}."""
        try:
            content = json.loads(text_data)['message'].strip()
        except (TypeError, ValueError, KeyError, AttributeError):
            return  # données invalides : on ignore
        if not content:
            return  # message vide : on ignore
        await self.save_message(content)  # ex02 : sauvegarde en base
        # On diffuse à tout le groupe (l'auteur le reçoit aussi et l'affiche).
        await self.channel_layer.group_send(self.group, {
            'type': 'chat.message',
            'user': self.user.username,
            'message': content,
        })

    async def broadcast_users(self):
        """Envoie à toute la room la liste (triée) des utilisateurs connectés."""
        await self.channel_layer.group_send(self.group, {
            'type': 'chat.users',
            'users': sorted(ONLINE.get(self.room_id, {})),
        })

    # --- Gestionnaires d'évènements de groupe ---------------------------
    # Le "type" d'un group_send ('chat.message') est converti en nom de méthode
    # ('chat_message'). Chaque connexion du groupe l'exécute et transmet le
    # résultat à son navigateur.
    async def chat_message(self, event):
        await self.send(json.dumps({
            'type': 'message',
            'user': event['user'],
            'message': event['message'],
        }))

    async def chat_system(self, event):
        await self.send(json.dumps({
            'type': 'system',
            'message': event['message'],
        }))

    async def chat_users(self, event):
        await self.send(json.dumps({
            'type': 'users',
            'users': event['users'],
        }))

    # --- Accès base de données ------------------------------------------
    # Le consumer est asynchrone mais l'ORM Django est synchrone :
    # database_sync_to_async exécute ces fonctions dans un thread dédié.
    @database_sync_to_async
    def room_exists(self):
        return Chatroom.objects.filter(pk=self.room_id).exists()

    @database_sync_to_async
    def save_message(self, content):
        Message.objects.create(room_id=self.room_id, user=self.user,
                               content=content)

    @database_sync_to_async
    def last_messages(self):
        # On prend les 3 plus récents (tri décroissant + [:3]) puis on inverse
        # pour renvoyer du plus ancien au plus récent.
        qs = (Message.objects.filter(room_id=self.room_id)
              .select_related('user').order_by('-created_at', '-id')
              [:HISTORY_SIZE])
        return [{'user': m.user.username, 'message': m.content}
                for m in reversed(list(qs))]
