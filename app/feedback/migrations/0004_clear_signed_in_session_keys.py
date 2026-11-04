from django.db import migrations


def clear_signed_in_session_keys(apps, schema_editor):
    """A signed-in commenter's session key signs in as them; only anonymous ones are kept."""
    Comment = apps.get_model('feedback', 'Comment')
    Comment.objects.filter(user__isnull=False).exclude(session_key='').update(session_key='')


class Migration(migrations.Migration):

    dependencies = [
        ('feedback', '0003_approve_existing_comments'),
    ]

    operations = [
        migrations.RunPython(clear_signed_in_session_keys, migrations.RunPython.noop),
    ]
