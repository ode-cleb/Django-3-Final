from django.urls import path

from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.room_list, name='room_list'),
    path('<int:room_id>/', views.room, name='room'),
]
