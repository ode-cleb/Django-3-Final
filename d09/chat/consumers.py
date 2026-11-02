"""Consumer websocket du chat (ex01 à ex03).

Un *consumer* est l'équivalent d'une vue pour les websockets : une instance de
ChatConsumer est créée pour CHAQUE connexion navigateur. Les utilisateurs d'une
même room sont regroupés dans un "groupe" Channels : un group_send() envoie un
évènement à toutes les connexions du groupe (c'est ce qui permet à un message de
parvenir à tout le monde).

Messages JSON envoyés au navigateur (champ "type") :
  - history : les messages à afficher à l'arrivée (ex02), avec "resumed" (voir plus bas)
  - message : un message d'utilisateur (avec son id en base)
  - system  : "<user> has joined/left the chat"
  - users   : la liste des utilisateurs connectés (ex03)

Rafraîchir la page (F5) ferme le websocket puis en rouvre un. Pour que ce ne soit
pas pris pour un vrai départ suivi d'une vraie arrivée, la présence est suivie par
ONGLET et non par connexion : chaque onglet a un identifiant "sid" (conservé par le
navigateur au travers des rechargements, voir chat.js) envoyé dans l'URL du websocket
(?sid=...&last=N, N = dernier message vu).
  - Une connexion dont le sid est DÉJÀ connu est une REPRISE, quel que soit l'ordre
    d'arrivée (nouvelle connexion avant OU après la fermeture de l'ancienne) :
    aucun "joined", et seuls les messages manqués (id > N) sont renvoyés.
  - Quand le dernier websocket d'un onglet se ferme, le "left" n'est annoncé qu'après
    LEAVE_GRACE_SECONDS ; une reprise dans ce délai l'annule.
  - Exception : si le navigateur a envoyé {"type": "leave"} (clic sur "← Rooms"), le
    départ est volontaire et le "left" est annoncé immédiatement.
"""
import asyncio
import json
import re
import secrets
from collections import defaultdict
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Chatroom, Message

# Nombre de messages envoyés à un NOUVEL arrivant (ex02).
HISTORY_SIZE = 3

# Délai (en secondes) avant d'annoncer qu'un utilisateur a quitté la room : laisse
# le temps à une page rafraîchie de se reconnecter sans que cela se remarque.
LEAVE_GRACE_SECONDS = 1

# Un sid valide : lettres, chiffres, "_" et "-" (8 à 64 caractères).
SID_RE = re.compile(r'^[A-Za-z0-9_-]{8,64}$')

# Suivi des utilisateurs connectés (ex03) :
#   ONLINE[room_id][username][sid] = nombre de websockets ouverts par cet onglet
# Un onglet a normalement 1 websocket, 2 pendant quelques instants lors d'un F5
# (l'ancien n'est pas encore fermé quand le nouveau arrive). Un utilisateur reste dans
# la liste tant qu'au moins un de ses onglets est présent.
# Un simple dict en mémoire suffit car le channel layer est lui aussi en mémoire
# (un seul processus serveur).
ONLINE = defaultdict(lambda: defaultdict(dict))

# Départs en attente (délai de grâce) : {(room_id, username, sid): tâche asyncio}.
PENDING = {}


async def finalize_leave(channel_layer, room_id, username, sid, group, delay):
    """Au bout du délai, si l'onglet n'est pas revenu : le retire de la liste puis
    annonce "left" et la nouvelle liste à ceux qui restent."""
    await asyncio.sleep(delay)

    # On se retire de PENDING AVANT de modifier l'état : à partir d'ici une
    # reconnexion ne peut plus annuler ce départ (elle sera traitée comme une arrivée).
    PENDING.pop((room_id, username, sid), None)

    tabs = ONLINE[room_id][username]
    if tabs.get(sid, 0) > 0:
        return  # un websocket de cet onglet s'est rouvert entre-temps
    tabs.pop(sid, None)
    if not tabs:
        del ONLINE[room_id][username]
    if not ONLINE[room_id]:
        del ONLINE[room_id]

    await channel_layer.group_send(group, {
        'type': 'chat.system',
        'message': f'{username} has left the chat',
    })
    await channel_layer.group_send(group, {
        'type': 'chat.users',
        'users': sorted(ONLINE.get(room_id, {})),
    })


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Appelée à l'ouverture du websocket."""
        self.user = self.scope['user']  # fourni par AuthMiddlewareStack (session Django)
        self.room_id = self.scope['url_route']['kwargs']['room_id']  # vient de routing.py
        self.group = f'chat_{self.room_id}'  # nom du groupe Channels de cette room
        self.leaving = False  # passe à True si le navigateur annonce un départ volontaire
        self.joined = False  # permet à disconnect() de savoir si la connexion a été acceptée

        # Chat réservé aux utilisateurs connectés, et la room doit exister.
        if not self.user.is_authenticated or not await self.room_exists():
            await self.close()
            return

        # Reprise après rafraîchissement ? Il faut que le navigateur donne l'identifiant
        # de son onglet (?sid=...) et le dernier message vu (?last=N), ET que cet onglet
        # soit déjà connu du serveur (websocket encore ouvert, ou départ en attente).
        self.sid, last = self.query_params()
        tabs = ONLINE[self.room_id][self.user.username]
        resumed = last is not None and self.sid in tabs
        if resumed:
            # Même onglet qui se reconnecte : on annule un éventuel départ en attente.
            task = PENDING.pop((self.room_id, self.user.username, self.sid), None)
            if task:
                task.cancel()
        # Ex03 : on compte ce websocket pour cet onglet (nouvel onglet => nouvelle entrée).
        tabs[self.sid] = tabs.get(self.sid, 0) + 1

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        self.joined = True

        if resumed:
            # Seuls les messages postés pendant le rechargement sont renvoyés ;
            # pas de "joined" : pour les autres, rien ne s'est passé.
            await self.send(json.dumps({
                'type': 'history',
                'resumed': True,
                'messages': await self.messages_after(last),
            }))
        else:
            # Ex02 : historique d'un nouvel arrivant (envoyé à lui seul), du plus
            # ancien au plus récent.
            await self.send(json.dumps({
                'type': 'history',
                'resumed': False,
                'messages': await self.last_messages(),
            }))
            # Ex01 : "<user> has joined the chat" pour tout le groupe, y compris
            # l'arrivant lui-même (il est déjà membre du groupe).
            await self.channel_layer.group_send(self.group, {
                'type': 'chat.system',
                'message': f'{self.user.username} has joined the chat',
            })
        # Ex03 : liste d'utilisateurs à jour pour tout le monde.
        await self.broadcast_users()

    async def disconnect(self, code):
        """Appelée quand le websocket se ferme (onglet fermé, F5, coupure réseau...)."""
        if not getattr(self, 'joined', False):
            return  # connexion refusée au départ : rien à nettoyer

        await self.channel_layer.group_discard(self.group, self.channel_name)

        # Ex03 : un websocket de moins pour cet onglet.
        tabs = ONLINE[self.room_id][self.user.username]
        tabs[self.sid] -= 1
        if tabs[self.sid] > 0:
            return  # un autre websocket du même onglet est ouvert (F5 en cours) : rien à annoncer

        # Dernier websocket de l'onglet : le "left" et le retrait de la liste sont
        # différés (voir finalize_leave) pour qu'un rechargement puisse annuler le départ.
        # Sauf départ volontaire (self.leaving) : il n'y a rien à annuler, délai nul.
        delay = 0 if self.leaving else LEAVE_GRACE_SECONDS
        PENDING[(self.room_id, self.user.username, self.sid)] = asyncio.ensure_future(
            finalize_leave(self.channel_layer, self.room_id, self.user.username,
                           self.sid, self.group, delay))

    async def receive(self, text_data=None, bytes_data=None):
        """Appelée quand le navigateur envoie :
          - {"message": "..."} : un message de chat ;
          - {"type": "leave"}  : "je quitte volontairement la room" (voir chat.js)."""
        try:
            data = json.loads(text_data)
            if data.get('type') == 'leave':
                # Départ volontaire : à la fermeture du socket, "left" sera immédiat.
                self.leaving = True
                return
            content = data['message'].strip()
        except (TypeError, ValueError, KeyError, AttributeError):
            return  # données invalides : on ignore
        if not content:
            return  # message vide : on ignore
        message_id = await self.save_message(content)  # ex02 : sauvegarde en base
        # On diffuse à tout le groupe (l'auteur le reçoit aussi et l'affiche).
        await self.channel_layer.group_send(self.group, {
            'type': 'chat.message',
            'id': message_id,
            'user': self.user.username,
            'message': content,
        })

    def query_params(self):
        """Lit ?sid=...&last=N dans l'URL du websocket.
        Renvoie (sid, last) : sid est généré côté serveur s'il manque ou est invalide
        (onglet non reprenable) ; last vaut None s'il manque ou est invalide."""
        query = parse_qs(self.scope.get('query_string', b'').decode())
        sid = query.get('sid', [''])[0]
        if not SID_RE.match(sid):
            sid = secrets.token_urlsafe(12)
            return sid, None
        try:
            last = int(query['last'][0])
        except (KeyError, IndexError, ValueError):
            last = None
        return sid, last

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
            'id': event['id'],
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
        # On renvoie l'id : le navigateur s'en sert pour savoir ce qu'il a déjà vu.
        return Message.objects.create(room_id=self.room_id, user=self.user,
                                      content=content).id

    @staticmethod
    def _serialize(messages):
        return [{'id': m.id, 'user': m.user.username, 'message': m.content}
                for m in messages]

    @database_sync_to_async
    def last_messages(self):
        # On prend les 3 plus récents (tri décroissant + [:3]) puis on inverse
        # pour renvoyer du plus ancien au plus récent.
        qs = (Message.objects.filter(room_id=self.room_id)
              .select_related('user').order_by('-created_at', '-id')
              [:HISTORY_SIZE])
        return self._serialize(reversed(list(qs)))

    @database_sync_to_async
    def messages_after(self, last_id):
        # Reprise : tous les messages postés après le dernier vu, du plus ancien au plus récent.
        qs = (Message.objects.filter(room_id=self.room_id, id__gt=last_id)
              .select_related('user').order_by('created_at', 'id'))
        return self._serialize(qs)
