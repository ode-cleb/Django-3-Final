from django.db import migrations

ROOMS = ['General', 'Python', 'Cats']


def create_rooms(apps, schema_editor):
    Chatroom = apps.get_model('chat', 'Chatroom')
    for name in ROOMS:
        Chatroom.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_rooms, migrations.RunPython.noop),
    ]
