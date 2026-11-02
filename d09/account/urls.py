from django.urls import path
from . import views

app_name = 'account'

urlpatterns = [
    path('', views.account_view, name='account'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
]