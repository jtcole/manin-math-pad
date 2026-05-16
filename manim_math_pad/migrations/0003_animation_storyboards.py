from django.db import migrations, models
import django.db.models.deletion
import uuid
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ('manim_math_pad', '0002_alter_animation_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnimationStoryboard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uid', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('concept', models.CharField(help_text='Math concept being storyboarded', max_length=255)),
                ('summary', models.TextField(blank=True, default='')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('rendering', 'Rendering clips'), ('completed', 'Completed'), ('failed', 'Failed'), ('canceled', 'Canceled')], default='pending', max_length=12)),
                ('created_at', models.DateTimeField(default=timezone.now)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict, help_text='Storyboard metadata: domain, clip titles, generation source, etc.')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='storyboards', to='manim_math_pad.session')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='animation',
            name='clip_count',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='animation',
            name='clip_index',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='animation',
            name='clip_summary',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='animation',
            name='clip_title',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='animation',
            name='storyboard',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='clips', to='manim_math_pad.animationstoryboard'),
        ),
    ]
