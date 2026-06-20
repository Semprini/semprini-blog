from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Comment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('entry_page_id', models.IntegerField(db_index=True)),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blog_comments', to='auth.user')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='Reaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('entry_page_id', models.IntegerField(db_index=True)),
                ('reaction_type', models.CharField(choices=[('upvote', '👍'), ('funny', '😄'), ('love', '❤️'), ('surprised', '😮'), ('angry', '😠'), ('sad', '😢')], max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reactions', to='auth.user')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='reaction',
            unique_together={('entry_page_id', 'user', 'reaction_type')},
        ),
    ]
