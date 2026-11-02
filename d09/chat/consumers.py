import json
from collections import defaultdict

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Chatroom, Message

HISTORY_SIZE = 3

# room_id -> {username: number of open connections}
# (a user with several tabs stays listed until the last one is closed).
# Valid because the in-memory channel layer is single-process anyway.
ONLINE = defaultdict(dict)


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.group = f'chat_{self.room_id}'
        self.joined = False

        if not self.user.is_authenticated or not await self.room_exists():
            await self.close()
            return

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        self.joined = True

        users = ONLINE[self.room_id]
        users[self.user.username] = users.get(self.user.username, 0) + 1

        # Ex02: last messages, oldest first, only for the newcomer.
        await self.send(json.dumps({
            'type': 'history',
            'messages': await self.last_messages(),
        }))
        # Ex01 + Ex03: "joined" notice and user list, for everybody
        # (the newcomer included, since he is part of the group).
        await self.channel_layer.group_send(self.group, {
            'type': 'chat.system',
            'message': f'{self.user.username} has joined the chat',
        })
        await self.broadcast_users()

    async def disconnect(self, code):
        if not getattr(self, 'joined', False):
            return
        users = ONLINE[self.room_id]
        users[self.user.username] -= 1
        if users[self.user.username] <= 0:
            del users[self.user.username]
        if not users:
            ONLINE.pop(self.room_id, None)

        await self.channel_layer.group_discard(self.group, self.channel_name)
        await self.channel_layer.group_send(self.group, {
            'type': 'chat.system',
            'message': f'{self.user.username} has left the chat',
        })
        await self.broadcast_users()

    async def receive(self, text_data=None, bytes_data=None):
        try:
            content = json.loads(text_data)['message'].strip()
        except (TypeError, ValueError, KeyError, AttributeError):
            return
        if not content:
            return
        await self.save_message(content)
        await self.channel_layer.group_send(self.group, {
            'type': 'chat.message',
            'user': self.user.username,
            'message': content,
        })

    async def broadcast_users(self):
        await self.channel_layer.group_send(self.group, {
            'type': 'chat.users',
            'users': sorted(ONLINE.get(self.room_id, {})),
        })

    # --- group event handlers -------------------------------------------
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

    # --- database helpers -----------------------------------------------
    @database_sync_to_async
    def room_exists(self):
        return Chatroom.objects.filter(pk=self.room_id).exists()

    @database_sync_to_async
    def save_message(self, content):
        Message.objects.create(room_id=self.room_id, user=self.user,
                               content=content)

    @database_sync_to_async
    def last_messages(self):
        qs = (Message.objects.filter(room_id=self.room_id)
              .select_related('user').order_by('-created_at', '-id')
              [:HISTORY_SIZE])
        return [{'user': m.user.username, 'message': m.content}
                for m in reversed(list(qs))]
