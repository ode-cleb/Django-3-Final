import asyncio
from unittest import mock

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


def communicator(room_id, user, last=None):
    # last : id du dernier message vu, comme le fait chat.js après un F5.
    query = f'?last={last}' if last is not None else ''
    c = WebsocketCommunicator(app, f'/ws/chat/{room_id}/{query}')
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


@mock.patch.object(consumers, 'LEAVE_GRACE_SECONDS', 0)
class ConsumerTests(TransactionTestCase):
    def setUp(self):
        consumers.ONLINE.clear()
        consumers.PENDING.clear()
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
        self.assertFalse(hist['resumed'])
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
            self.assertEqual((got['type'], got['user'], got['message']),
                             ('message', 'alice', 'hello'))
            self.assertIsInstance(got['id'], int)
        self.assertEqual(await database_sync_to_async(
            Message.objects.filter(content='hello').count)(), 1)

        await b.disconnect()
        self.assertEqual((await a.receive_json_from())['message'],
                         'bob has left the chat')
        self.assertEqual((await a.receive_json_from())['users'], ['alice'])
        await a.disconnect()


class RefreshTests(TransactionTestCase):
    """F5 dans une room : le websocket se ferme puis se rouvre."""

    def setUp(self):
        consumers.ONLINE.clear()
        consumers.PENDING.clear()
        self.room = Chatroom.objects.create(name='test-room')
        self.alice = CustomUser.objects.create_user('alice', password='x')
        self.bob = CustomUser.objects.create_user('bob', password='x')

    async def _start(self):
        """alice et bob dans la room, 5 messages échangés. Renvoie (a, b, id du dernier)."""
        a = communicator(self.room.id, self.alice)
        b = communicator(self.room.id, self.bob)
        await a.connect()
        await b.connect()
        await a.receive_nothing(timeout=0.2)  # laisse passer joined/users
        while not await a.receive_nothing(timeout=0.05):
            await a.receive_json_from()
        while not await b.receive_nothing(timeout=0.05):
            await b.receive_json_from()
        last = None
        for i in range(5):
            await a.send_json_to({'message': f'm{i}'})
            last = (await a.receive_json_from())['id']
            await b.receive_json_from()
        return a, b, last

    @mock.patch.object(consumers, 'LEAVE_GRACE_SECONDS', 5)
    async def test_refresh_is_silent_and_resumed(self):
        a, b, last = await self._start()

        await b.disconnect()                       # F5 : l'ancien websocket se ferme...
        # ... pendant ce temps alice poste un message que bob va manquer
        await a.send_json_to({'message': 'while you reload'})
        missed_id = (await a.receive_json_from())['id']

        b2 = communicator(self.room.id, self.bob, last=last)   # ... et un nouveau s'ouvre
        self.assertTrue((await b2.connect())[0])
        hist = await b2.receive_json_from()
        self.assertTrue(hist['resumed'])
        # seulement le message manqué, pas les 3 derniers
        self.assertEqual([(m['id'], m['message']) for m in hist['messages']],
                         [(missed_id, 'while you reload')])
        self.assertEqual((await b2.receive_json_from())['users'], ['alice', 'bob'])

        # alice ne reçoit ni "left" ni "joined" : seulement la liste inchangée
        got = await a.receive_json_from()
        self.assertEqual((got['type'], got['users']), ('users', ['alice', 'bob']))
        self.assertTrue(await a.receive_nothing(timeout=0.3))
        self.assertEqual(consumers.ONLINE[self.room.id], {'alice': 1, 'bob': 1})
        self.assertFalse(consumers.PENDING)

        await a.disconnect()
        await b2.disconnect()
        for t in list(consumers.PENDING.values()):
            for task in t:
                task.cancel()

    @mock.patch.object(consumers, 'LEAVE_GRACE_SECONDS', 0.05)
    async def test_reconnect_after_grace_is_a_real_leave_and_join(self):
        a, b, last = await self._start()
        await b.disconnect()
        await asyncio.sleep(0.3)                   # délai de grâce dépassé
        self.assertEqual((await a.receive_json_from())['message'],
                         'bob has left the chat')
        self.assertEqual((await a.receive_json_from())['users'], ['alice'])

        b2 = communicator(self.room.id, self.bob, last=last)
        await b2.connect()
        hist = await b2.receive_json_from()
        self.assertFalse(hist['resumed'])
        self.assertEqual([m['message'] for m in hist['messages']],
                         ['m2', 'm3', 'm4'])      # nouvel arrivant : 3 derniers
        self.assertEqual((await a.receive_json_from())['message'],
                         'bob has joined the chat')
        await a.disconnect()
        await b2.disconnect()
        await asyncio.sleep(0.2)

    @mock.patch.object(consumers, 'LEAVE_GRACE_SECONDS', 5)
    async def test_last_param_without_pending_leave_is_not_a_resume(self):
        # ?last=... mais personne en attente : c'est une arrivée normale.
        a = communicator(self.room.id, self.alice, last=0)
        await a.connect()
        hist = await a.receive_json_from()
        self.assertFalse(hist['resumed'])
        self.assertEqual((await a.receive_json_from())['message'],
                         'alice has joined the chat')
        await a.disconnect()
        for t in list(consumers.PENDING.values()):
            for task in t:
                task.cancel()
