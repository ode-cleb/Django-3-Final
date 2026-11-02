from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .models import Chatroom


def room_list(request):
    """Ex01 : page listant un lien par chatroom (les noms viennent de la base)."""
    return render(request, 'chat/room_list.html',
                  {'rooms': Chatroom.objects.order_by('id')})


@login_required  # utilisateur anonyme -> redirigé vers /account/ (settings.LOGIN_URL)
def room(request, room_id):
    """Page d'un chat. Elle ne fait qu'afficher le squelette HTML : les messages
    arrivent ensuite par websocket (voir chat.js et consumers.py)."""
    chatroom = get_object_or_404(Chatroom, pk=room_id)
    return render(request, 'chat/room.html', {'room': chatroom})
