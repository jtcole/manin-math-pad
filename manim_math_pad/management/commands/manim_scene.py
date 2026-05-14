"""Generate Manim scene code from the command line."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from ...engine.renderer import ManimRenderer
from ...engine.scene_generator import SceneGenerator


class Command(BaseCommand):
    """Generate a Manim scene for a concept.

    Django exposes this command as `manage.py manim_scene`; it is the
    Django-compatible equivalent of the requested manim-scene command name.
    """

    help = 'Generate Manim scene code for a math concept.'

    def add_arguments(self, parser):
        parser.add_argument('concept', nargs='+', help='Concept description to animate.')
        parser.add_argument(
            '--scene-model',
            default=None,
            help='LLM model for novel scene generation.',
        )
        parser.add_argument(
            '--no-llm',
            action='store_true',
            help='Use only built-in templates and placeholder scenes.',
        )
        parser.add_argument(
            '--output',
            default=None,
            help='Write generated Python code to this file.',
        )
        parser.add_argument(
            '--render',
            action='store_true',
            help='Render the generated scene after writing it.',
        )
        parser.add_argument(
            '--quality',
            default='medium_quality',
            choices=['low_quality', 'medium_quality', 'high_quality', 'production_quality'],
            help='Manim quality preset when --render is used.',
        )
        parser.add_argument('--fps', type=int, default=30, help='Rendered frames per second.')
        parser.add_argument('--timeout', type=int, default=120, help='Render timeout in seconds.')

    def handle(self, *args, **options):
        concept = ' '.join(options['concept'])
        generator = SceneGenerator(
            enable_llm=not options['no_llm'],
            scene_model=options['scene_model'],
        )
        generated = generator.generate(concept)

        if options['output']:
            output_path = Path(options['output'])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(generated.scene_code, encoding='utf-8')
            self.stdout.write(f'Wrote {generated.source} scene to {output_path}')
        else:
            self.stdout.write(generated.scene_code)

        if not options['render']:
            return

        renderer = ManimRenderer(
            output_dir=self._render_output_dir(),
            quality=options['quality'],
            fps=options['fps'],
        )
        result = renderer.render(
            generated.scene_code,
            generated.scene_name,
            timeout=options['timeout'],
        )

        if result.success:
            self.stdout.write(self.style.SUCCESS(f'Rendered video: {result.video_path}'))
            if result.thumbnail_path:
                self.stdout.write(f'Thumbnail: {result.thumbnail_path}')
        else:
            self.stderr.write(self.style.ERROR(result.error_message))

    def _render_output_dir(self) -> Path:
        media_root = Path(getattr(settings, 'MEDIA_ROOT', '') or '/tmp/manim_math_pad_media')
        return media_root / 'manim' / 'manual_renders'
