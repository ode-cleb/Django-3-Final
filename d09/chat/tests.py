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


def communicator(room_id, user, last=None, sid=None):
    # sid : identifiant de l'onglet ; last : id du dernier message vu.
    # Ce sont les paramètres que chat.js envoie, notamment après un F5.
    params = []
    if sid is not None:
        params.append(f'sid={sid}')
    if last is not None:
        params.append(f'last={last}')
    query = '?' + '&'.join(params) if params else ''
    c = WebsocketCommunicator(app, f'/ws/chat/{room_id}/{query}')
    c.scope['user'] = user
    return c


class ViewTests(TestCase):
    def test_pages_do_not_show_raw_template_comments(self):
        """Un {# ... #} sur plusieurs lignes n'est pas un commentaire Django : il
        s'afficherait tel quel dans la page."""
        user = CustomUser.objects.create_user('zoe', password='x')
        self.client.force_login(user)
        room = Chatroom.objects.first()
        for url in (reverse('account:account'), reverse('chat:room_list'),
                    reverse('chat:room', args=[room.id])):
            html = self.client.get(url).content.decode()
            self.assertNotIn('{#', html, url)
            self.assertNotIn('#}', html, url)
        self.client.logout()
        html = self.client.get(reverse('account:account')).content.decode()
        self.assertNotIn('{#', html)
        self.assertNotIn('#}', html)

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

    def tearDown(self):
        for task in list(consumers.PENDING.values()):
            task.cancel()

    async def _drain(self, *comms):
        for c in comms:
            while not await c.receive_nothing(timeout=0.05):
                await c.receive_json_from()

    async def _start(self):
        """alice et bob dans la room, 5 messages échangés. Renvoie (a, b, id du dernier)."""
        a = communicator(self.room.id, self.alice, last=0, sid='sid-alice-0001')
        b = communicator(self.room.id, self.bob, last=0, sid='sid-bob-000001')
        await a.connect()
        await b.connect()
        await self._drain(a, b)
        last = None
        for i in range(5):
            await a.send_json_to({'message': f'm{i}'})
            last = (await a.receive_json_from())['id']
            await b.receive_json_from()
        return a, b, last

    async def _assert_silent_resume(self, a, b2, missed):
        """b2 a repris la place de bob : seulement les messages manqués, et alice ne
        reçoit ni "left" ni "joined" (même une fois le délai de grâce écoulé)."""
        hist = await b2.receive_json_from()
        self.assertTrue(hist['resumed'])
        self.assertEqual([m['message'] for m in hist['messages']], missed)
        self.assertEqual((await b2.receive_json_from())['users'], ['alice', 'bob'])
        got = await a.receive_json_from()
        self.assertEqual((got['type'], got['users']), ('users', ['alice', 'bob']))
        self.assertTrue(await a.receive_nothing(timeout=0.4))

    @mock.patch.object(consumers, 'LEAVE_GRACE_SECONDS', 0.2)
    async def test_refresh_old_socket_closed_first(self):
        """F5 "classique" : l'ancien websocket se ferme, puis le nouveau s'ouvre."""
        a, b, last = await self._start()
        await b.disconnect()
        await a.send_json_to({'message': 'while you reload'})   # bob la manque
        await a.receive_json_from()
        b2 = communicator(self.room.id, self.bob, last=last, sid='sid-bob-000001')
        self.assertTrue((await b2.connect())[0])
        await self._assert_silent_resume(a, b2, ['while you reload'])
        self.assertEqual({u: dict(t) for u, t in consumers.ONLINE[self.room.id].items()},
                         {'alice': {'sid-alice-0001': 1}, 'bob': {'sid-bob-000001': 1}})
        self.assertFalse(consumers.PENDING)
        await a.disconnect()
        await b2.disconnect()

    @mock.patch.object(consumers, 'LEAVE_GRACE_SECONDS', 0.2)
    async def test_refresh_new_socket_arrives_before_old_one_closes(self):
        """La course vue dans un vrai navigateur : le nouveau websocket arrive AVANT
        que le serveur ait reçu la fermeture de l'ancien."""
        a, b, last = await self._start()
        b2 = communicator(self.room.id, self.bob, last=last, sid='sid-bob-000001')
        self.assertTrue((await b2.connect())[0])      # b est encore ouvert
        await self._assert_silent_resume(a, b2, [])
        await b.disconnect()                          # la fermeture de l'ancien arrive après
        self.assertTrue(await a.receive_nothing(timeout=0.5))   # (délai de grâce dépassé)
        self.assertEqual({u: dict(t) for u, t in consumers.ONLINE[self.room.id].items()},
                         {'alice': {'sid-alice-0001': 1}, 'bob': {'sid-bob-000001': 1}})
        self.assertFalse(consumers.PENDING)
        await a.disconnect()
        await b2.disconnect()

    @mock.patch.object(consumers, 'LEAVE_GRACE_SECONDS', 0.05)
    async def test_reconnect_after_grace_is_a_real_leave_and_join(self):
        a, b, last = await self._start()
        await b.disconnect()
        await asyncio.sleep(0.3)                   # délai de grâce dépassé
        self.assertEqual((await a.receive_json_from())['message'],
                         'bob has left the chat')
        self.assertEqual((await a.receive_json_from())['users'], ['alice'])

        b2 = communicator(self.room.id, self.bob, last=last, sid='sid-bob-000001')
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

    @mock.patch.object(consumers, 'LEAVE_GRACE_SECONDS', 0.05)
    async def test_two_tabs_of_same_user_are_independent(self):
        a, b, last = await self._start()
        b2 = communicator(self.room.id, self.bob, last=0, sid='sid-bob-tab-two')
        await b2.connect()
        hist = await b2.receive_json_from()
        self.assertFalse(hist['resumed'])           # autre onglet : vraie arrivée
        await self._drain(a, b, b2)
        await b2.disconnect()                       # l'onglet 2 se ferme...
        await asyncio.sleep(0.2)
        self.assertEqual((await a.receive_json_from())['message'],
                         'bob has left the chat')
        self.assertEqual((await a.receive_json_from())['users'], ['alice', 'bob'])
        await a.disconnect()
        await b.disconnect()
        await asyncio.sleep(0.2)

    @mock.patch.object(consumers, 'LEAVE_GRACE_SECONDS', 0.05)
    async def test_missing_or_invalid_sid_is_a_new_arrival(self):
        a = communicator(self.room.id, self.alice, last=0)            # sans sid
        await a.connect()
        self.assertFalse((await a.receive_json_from())['resumed'])
        self.assertEqual((await a.receive_json_from())['message'],
                         'alice has joined the chat')
        a2 = communicator(self.room.id, self.alice, last=0, sid='no good!')   # sid invalide
        await a2.connect()
        self.assertFalse((await a2.receive_json_from())['resumed'])
        await a.disconnect()
        await a2.disconnect()
        await asyncio.sleep(0.2)
