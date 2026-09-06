import django.core.validators
from django.db import migrations, models

TUNING = ("speed", "stability", "similarity_boost", "style", "use_speaker_boost")


def split_settings(apps, schema_editor):
    """Move the hand-typed JSON into real columns.

    The values must survive intact: they feed ``Voice.tuning_rev``, and a
    changed fingerprint would orphan every rendition already paid for.
    """
    Voice = apps.get_model("devcast", "Voice")
    for voice in Voice.objects.all():
        settings = dict(voice.settings or {})
        for name in TUNING:
            if name in settings:
                setattr(voice, name, settings.pop(name))
        voice.extra_settings = settings
        voice.save()


def merge_settings(apps, schema_editor):
    Voice = apps.get_model("devcast", "Voice")
    for voice in Voice.objects.all():
        settings = dict(voice.extra_settings or {})
        for name in TUNING:
            value = getattr(voice, name)
            if value is not None:
                settings[name] = value
        voice.settings = settings
        voice.save()


class Migration(migrations.Migration):

    dependencies = [
        ("devcast", "0004_audioentrypage_voice"),
    ]

    operations = [
        migrations.AddField(
            model_name="voice",
            name="extra_settings",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Escape hatch for engine parameters that have no field above. Merged into the request as-is.",
            ),
        ),
        migrations.AddField(
            model_name="voice",
            name="speed",
            field=models.FloatField(
                blank=True,
                help_text="0.7 slowest to 1.2 fastest. 1.0 is unmodified. Empty uses 1.0.",
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0.7),
                    django.core.validators.MaxValueValidator(1.2),
                ],
            ),
        ),
        migrations.AddField(
            model_name="voice",
            name="stability",
            field=models.FloatField(
                blank=True,
                help_text="0.0 to 1.0. Lower is more expressive and more variable between renders; higher is steadier but flatter. Empty uses 0.5.",
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0.0),
                    django.core.validators.MaxValueValidator(1.0),
                ],
            ),
        ),
        migrations.AddField(
            model_name="voice",
            name="similarity_boost",
            field=models.FloatField(
                blank=True,
                help_text="0.0 to 1.0. How closely to match the original voice. Very high values can reproduce artefacts from the source recording. Empty uses 0.75.",
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0.0),
                    django.core.validators.MaxValueValidator(1.0),
                ],
                verbose_name="similarity",
            ),
        ),
        migrations.AddField(
            model_name="voice",
            name="style",
            field=models.FloatField(
                blank=True,
                help_text="0.0 to 1.0. Amplifies the speaker's delivery. Anything above 0 costs latency and can destabilise long passages. Empty uses 0.0.",
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0.0),
                    django.core.validators.MaxValueValidator(1.0),
                ],
                verbose_name="style exaggeration",
            ),
        ),
        migrations.AddField(
            model_name="voice",
            name="use_speaker_boost",
            field=models.BooleanField(
                blank=True,
                help_text="Increases similarity to the original speaker. Empty uses on.",
                null=True,
            ),
        ),
        migrations.RunPython(split_settings, merge_settings),
        migrations.RemoveField(
            model_name="voice",
            name="settings",
        ),
    ]
