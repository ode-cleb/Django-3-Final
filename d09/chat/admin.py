from django.contrib import admin

from .models import Chatroom, Message

# Permet de gérer les rooms et de voir les messages depuis /admin/.
admin.site.register(Chatroom)
admin.site.register(Message)
