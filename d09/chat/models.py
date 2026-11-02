from django.conf import settings
from django.db import models


class Chatroom(models.Model):
    """Une chatroom. Les noms sont en base de données (ex01) ; trois rooms par
    défaut sont créées par la migration 0002_default_chatrooms."""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Message(models.Model):
    """Un message posté dans une room (ex02 : sert à reconstituer l'historique)."""
    room = models.ForeignKey(Chatroom, on_delete=models.CASCADE,
                             related_name='messages')
    # AUTH_USER_MODEL = notre CustomUser ; related_name='+' : pas de relation inverse.
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE, related_name='+')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Du plus ancien au plus récent par défaut.
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.user}: {self.content[:30]}'
