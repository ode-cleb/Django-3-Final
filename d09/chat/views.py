from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .models import Chatroom


def room_list(request):
    return render(request, 'chat/room_list.html',
                  {'rooms': Chatroom.objects.order_by('id')})


@login_required
def room(request, room_id):
    chatroom = get_object_or_404(Chatroom, pk=room_id)
    return render(request, 'chat/room.html', {'room': chatroom})
