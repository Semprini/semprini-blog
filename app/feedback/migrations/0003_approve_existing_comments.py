from django.db import migrations


def approve_existing(apps, schema_editor):
    """Comments that predate moderation were already public; keep them that way."""
    Comment = apps.get_model('feedback', 'Comment')
    Comment.objects.update(is_approved=True)


def unapprove_all(apps, schema_editor):
    Comment = apps.get_model('feedback', 'Comment')
    Comment.objects.update(is_approved=False)


class Migration(migrations.Migration):

    dependencies = [
        ('feedback', '0002_public_comments'),
    ]

    operations = [
        migrations.RunPython(approve_existing, unapprove_all),
    ]
