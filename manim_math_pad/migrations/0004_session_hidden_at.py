from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('manim_math_pad', '0003_animation_storyboards'),
    ]

    operations = [
        migrations.AddField(
            model_name='session',
            name='hidden_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
