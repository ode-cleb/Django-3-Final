from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from account.models import CustomUser
from . import consumers
from .models import Chatroom, Message
from .routing import websocket_urlpatterns

app = URLRouter(websocket_urlpatterns)


def communicator(room_id, user):
    c = WebsocketCommunicator(app, f'/ws/chat/{room_id}/')
    c.scope['user'] = user
    return c


class ViewTests(TestCase):
    def test_three_default_rooms(self):
        r = self.client.get(reverse('chat:room_list'))
        self.assertEqual(Chatroom.objects.count(), 3)
        for room in Chatroom.objects.all():
            self.assertContains(r, reverse('chat:room', args=[room.id]))

    def test_room_requires_login(self):
        room = Chatroom.objects.first()
        r = self.client.get(reverse('chat:room', args=[room.id]))
        self.assertEqual(r.status_code, 302)
        user = CustomUser.objects.create_user('bob', password='x')
        self.client.force_login(user)
        r = self.client.get(reverse('chat:room', args=[room.id]))
        self.assertContains(r, room.name)


class ConsumerTests(TransactionTestCase):
    def setUp(self):
        consumers.ONLINE.clear()
        self.room = Chatroom.objects.create(name='test-room')
        self.alice = CustomUser.objects.create_user('alice', password='x')
        self.bob = CustomUser.objects.create_user('bob', password='x')

    async def test_anonymous_rejected(self):
        c = communicator(self.room.id, AnonymousUser())
        connected, _ = await c.connect()
        self.assertFalse(connected)

    async def test_join_message_users_history_and_leave(self):
        for i in range(5):
            await database_sync_to_async(Message.objects.create)(
                room=self.room, user=self.alice, content=f'old{i}')

        a = communicator(self.room.id, self.alice)
        self.assertTrue((await a.connect())[0])
        hist = await a.receive_json_from()
        self.assertEqual([m['message'] for m in hist['messages']],
                         ['old2', 'old3', 'old4'])
        self.assertEqual((await a.receive_json_from())['message'],
                         'alice has joined the chat')
        self.assertEqual((await a.receive_json_from())['users'], ['alice'])

        b = communicator(self.room.id, self.bob)
        await b.connect()
        await b.receive_json_from()  # history
        self.assertEqual((await b.receive_json_from())['message'],
                         'bob has joined the chat')
        self.assertEqual((await b.receive_json_from())['users'], ['alice', 'bob'])
        self.assertEqual((await a.receive_json_from())['message'],
                         'bob has joined the chat')
        self.assertEqual((await a.receive_json_from())['users'], ['alice', 'bob'])

        await a.send_json_to({'message': 'hello'})
        for c in (a, b):
            got = await c.receive_json_from()
            self.assertEqual(got, {'type': 'message', 'user': 'alice',
                                   'message': 'hello'})
        self.assertEqual(await database_sync_to_async(
            Message.objects.filter(content='hello').count)(), 1)

        await b.disconnect()
        self.assertEqual((await a.receive_json_from())['message'],
                         'bob has left the chat')
        self.assertEqual((await a.receive_json_from())['users'], ['alice'])
        await a.disconnect()
