"""Render pending Manim Math Pad animations."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ...engine.renderer import ManimRenderer
from ...engine.scene_generator import LLMSceneGenerator, SceneGenerator
from ...models import Animation

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Poll pending Animation rows and render them with Manim."""

    help = 'Process pending Manim Math Pad animation render jobs.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Process at most one pending animation and exit.',
        )
        parser.add_argument(
            '--sleep',
            type=float,
            default=5.0,
            help='Seconds to sleep between polling attempts when not using --once.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maximum number of animations to process before exiting.',
        )
        parser.add_argument(
            '--quality',
            default='medium_quality',
            choices=['low_quality', 'medium_quality', 'high_quality', 'production_quality'],
            help='Manim quality preset.',
        )
        parser.add_argument('--fps', type=int, default=30, help='Rendered frames per second.')
        parser.add_argument(
            '--timeout',
            type=int,
            default=120,
            help='Maximum seconds allowed for each Manim render.',
        )
        parser.add_argument(
            '--manim-cmd',
            default='manim',
            help='Manim executable path.',
        )
        parser.add_argument(
            '--skip-storyboard-concat',
            action='store_true',
            help='Do not assemble completed storyboard clips into a combined MP4.',
        )
        parser.add_argument(
            '--scene-model',
            default=None,
            help='LLM model to use if an animation is missing scene code.',
        )

    def handle(self, *args, **options):
        once = options['once']
        limit = options['limit']
        processed = 0

        self.stdout.write('Starting Manim render queue worker')

        while True:
            animation = self._claim_next_animation()
            if not animation:
                if once:
                    self.stdout.write('No pending animations.')
                    return
                time.sleep(options['sleep'])
                continue

            self._process_animation(animation, options)
            processed += 1

            if once or (limit is not None and processed >= limit):
                self.stdout.write(f'Processed {processed} animation(s).')
                return

    def _claim_next_animation(self) -> Animation | None:
        """Claim the oldest pending animation and move it into generating."""
        with transaction.atomic():
            animation = (
                Animation.objects.select_for_update()
                .filter(status='pending')
                .order_by('created_at')
                .first()
            )
            if not animation:
                return None

            self._log_transition(animation, animation.status, 'generating')
            animation.status = 'generating'
            animation.error_message = ''
            animation.save(update_fields=['status', 'error_message'])
            self._sync_storyboard(animation)
            return animation

    def _process_animation(self, animation: Animation, options: dict) -> None:
        self.stdout.write(f'Processing animation {animation.uid}: {animation.concept}')

        try:
            # Check if canceled before generating scene
            animation.refresh_from_db()
            if animation.status == 'canceled':
                self.stdout.write(f'Skipped canceled animation {animation.uid}')
                return

            scene_name = self._ensure_scene_code(animation, options.get('scene_model'))
            self._mark_rendering(animation, scene_name)

            # Check if canceled before rendering
            animation.refresh_from_db()
            if animation.status == 'canceled':
                self.stdout.write(f'Skipped canceled animation {animation.uid}')
                return

            renderer = ManimRenderer(
                output_dir=self._render_output_dir(),
                quality=options['quality'],
                fps=options['fps'],
                manim_cmd=options['manim_cmd'],
            )
            result = renderer.render(
                animation.scene_code,
                scene_name,
                job_uid=str(animation.uid),
                timeout=options['timeout'],
            )

            if not result.success:
                self._mark_failed(animation, result.error_message, result.metadata or {})
                return

            self._mark_completed(animation, result, skip_storyboard_concat=options.get('skip_storyboard_concat', False))
            self.stdout.write(self.style.SUCCESS(f'Completed animation {animation.uid}'))
        except Exception as exc:
            logger.exception('Animation render failed for %s', animation.uid)
            self._mark_failed(animation, str(exc), {})

    def _ensure_scene_code(self, animation: Animation, scene_model: str | None) -> str:
        """Ensure the job has scene code and return the scene class name."""
        metadata = animation.metadata or {}
        scene_name = metadata.get('scene_name')

        if not animation.scene_code:
            generator = SceneGenerator(enable_llm=True, scene_model=scene_model)
            generated = generator.generate(animation.concept, context=animation.session.context)
            animation.scene_code = generated.scene_code
            scene_name = generated.scene_name
            metadata.update(
                {
                    'source': generated.source,
                    'scene_name': generated.scene_name,
                    'generation': generated.metadata,
                }
            )
            animation.metadata = metadata
            animation.save(update_fields=['scene_code', 'metadata'])

        if not scene_name:
            scene_name = LLMSceneGenerator.extract_scene_name(animation.scene_code)

        if not scene_name:
            raise ValueError('Could not determine Manim scene class name')

        return scene_name

    def _mark_rendering(self, animation: Animation, scene_name: str) -> None:
        metadata = animation.metadata or {}
        metadata['scene_name'] = scene_name
        animation.metadata = metadata
        self._log_transition(animation, animation.status, 'rendering')
        animation.status = 'rendering'
        animation.save(update_fields=['metadata', 'status'])
        self._sync_storyboard(animation)

    def _mark_completed(
        self,
        animation: Animation,
        result,
        skip_storyboard_concat: bool = False,
    ) -> None:
        metadata = animation.metadata or {}
        metadata.update(result.metadata or {})
        animation.metadata = metadata
        self._log_transition(animation, animation.status, 'completed')
        animation.status = 'completed'
        animation.error_message = ''
        animation.completed_at = timezone.now()
        animation.duration_seconds = result.duration_seconds

        if result.video_path:
            with Path(result.video_path).open('rb') as video_file:
                animation.video_file.save(
                    f'{animation.uid}.{Path(result.video_path).suffix.lstrip(".")}',
                    File(video_file),
                    save=False,
                )

        if result.thumbnail_path:
            with Path(result.thumbnail_path).open('rb') as thumbnail_file:
                animation.thumbnail_file.save(
                    f'{animation.uid}.jpg',
                    File(thumbnail_file),
                    save=False,
                )

        animation.save()
        self._sync_storyboard(animation)
        if animation.storyboard_id and not skip_storyboard_concat:
            self._assemble_storyboard(animation.storyboard)

    def _mark_failed(self, animation: Animation, error_message: str, metadata: dict) -> None:
        existing_metadata = animation.metadata or {}
        existing_metadata.update(metadata)
        animation.metadata = existing_metadata
        self._log_transition(animation, animation.status, 'failed')
        animation.status = 'failed'
        animation.error_message = (error_message or 'Unknown render failure')[:2000]
        animation.completed_at = timezone.now()
        animation.save(update_fields=['metadata', 'status', 'error_message', 'completed_at'])
        self._sync_storyboard(animation)
        self.stderr.write(self.style.ERROR(f'Failed animation {animation.uid}: {error_message}'))

    def _render_output_dir(self) -> Path:
        media_root = Path(getattr(settings, 'MEDIA_ROOT', '') or '/tmp/manim_math_pad_media')
        return media_root / 'manim' / 'render_queue'

    def _storyboard_output_dir(self) -> Path:
        media_root = Path(getattr(settings, 'MEDIA_ROOT', '') or '/tmp/manim_math_pad_media')
        return media_root / 'manim' / 'storyboards'

    def _log_transition(self, animation: Animation, old_status: str, new_status: str) -> None:
        message = f'Animation {animation.uid}: {old_status} -> {new_status}'
        logger.info(message)
        self.stdout.write(message)

    def _sync_storyboard(self, animation: Animation) -> None:
        if not animation.storyboard_id:
            return

        storyboard = animation.storyboard
        statuses = set(storyboard.clips.values_list('status', flat=True))
        if statuses <= {'completed'}:
            status = 'completed'
        elif statuses <= {'canceled'}:
            status = 'canceled'
        elif 'failed' in statuses:
            status = 'failed'
        elif statuses & {'generating', 'rendering', 'completed'}:
            status = 'rendering'
        else:
            status = 'pending'

        terminal = status in {'completed', 'failed', 'canceled'}
        update_fields = []
        if storyboard.status != status:
            storyboard.status = status
            update_fields.append('status')
        if terminal and storyboard.completed_at is None:
            storyboard.completed_at = timezone.now()
            update_fields.append('completed_at')
        if not terminal and storyboard.completed_at is not None:
            storyboard.completed_at = None
            update_fields.append('completed_at')
        if update_fields:
            storyboard.save(update_fields=update_fields)

    def _assemble_storyboard(self, storyboard) -> None:
        storyboard.refresh_from_db()
        clips = list(storyboard.clips.order_by('clip_index', 'created_at'))
        if not clips or any(clip.status != 'completed' or not clip.video_file for clip in clips):
            return

        clip_paths = []
        for clip in clips:
            try:
                clip_paths.append(Path(clip.video_file.path))
            except (NotImplementedError, ValueError):
                return

        output_dir = self._storyboard_output_dir()
        renderer = ManimRenderer(output_dir=output_dir)
        result = renderer.concatenate_videos(
            clip_paths,
            output_dir / f'{storyboard.uid}.mp4',
            thumbnail_path=output_dir / f'{storyboard.uid}.jpg',
        )
        metadata = storyboard.metadata or {}
        captions_path = None
        if result.success:
            captions_path = output_dir / f'{storyboard.uid}.vtt'
            captions_path.write_text(
                self._storyboard_captions_vtt(
                    clips,
                    result.duration_seconds,
                    lesson=metadata.get('lesson_artifact'),
                ),
                encoding='utf-8',
            )

        assemblies = metadata.get('assemblies') or []
        assembly = {
            'status': 'completed' if result.success else 'failed',
            'video_path': str(result.video_path) if result.video_path else '',
            'thumbnail_path': str(result.thumbnail_path) if result.thumbnail_path else '',
            'captions_path': str(captions_path) if captions_path else '',
            'duration_seconds': result.duration_seconds,
            'clip_count': len(clips),
            'error': result.error_message,
            'metadata': result.metadata or {},
        }
        metadata.update(
            {
                'combined_video_path': assembly['video_path'],
                'combined_thumbnail_path': assembly['thumbnail_path'],
                'combined_captions_path': assembly['captions_path'],
                'combined_duration_seconds': assembly['duration_seconds'],
                'combined_status': assembly['status'],
                'combined_error': assembly['error'],
                'assemblies': [*assemblies, assembly][-5:],
            }
        )
        storyboard.metadata = metadata
        storyboard.save(update_fields=['metadata'])

    def _storyboard_captions_vtt(
        self,
        clips: list[Animation],
        duration_seconds: float | None,
        lesson: dict | None = None,
    ) -> str:
        if isinstance(lesson, dict) and lesson.get('subtitles'):
            return self._lesson_captions_vtt(lesson)

        lines = ['WEBVTT', '']
        fallback_duration = 5.0
        if duration_seconds and clips:
            fallback_duration = max(float(duration_seconds) / len(clips), 1.0)

        cursor = 0.0
        for index, clip in enumerate(clips, start=1):
            clip_duration = self._clip_caption_duration(clip, fallback_duration)
            start = cursor
            end = cursor + clip_duration
            lines.extend(
                [
                    str(index),
                    f'{self._vtt_time(start)} --> {self._vtt_time(end)}',
                    self._clip_caption_text(clip),
                    '',
                ]
            )
            cursor = end
        return '\n'.join(lines)

    def _lesson_captions_vtt(self, lesson: dict) -> str:
        lines = ['WEBVTT', '']
        for subtitle in lesson.get('subtitles') or []:
            lines.extend(
                [
                    str(subtitle.get('index', '')),
                    (
                        f'{self._vtt_time(float(subtitle.get("start_seconds") or 0))} --> '
                        f'{self._vtt_time(float(subtitle.get("end_seconds") or 0))}'
                    ),
                    ' '.join(str(subtitle.get('text') or '').split()),
                    '',
                ]
            )
        return '\n'.join(lines)

    def _clip_caption_duration(self, clip: Animation, fallback_duration: float) -> float:
        metadata = clip.metadata or {}
        for value in [clip.duration_seconds, metadata.get('target_duration_seconds')]:
            if value is None:
                continue
            try:
                duration = float(value)
            except (TypeError, ValueError):
                continue
            if duration > 0:
                return duration
        return fallback_duration

    def _clip_caption_text(self, clip: Animation) -> str:
        metadata = clip.metadata or {}
        text = (
            clip.clip_summary
            or metadata.get('clip_purpose')
            or metadata.get('clip_title')
            or clip.clip_title
            or clip.concept
        )
        return ' '.join(str(text).split())

    def _vtt_time(self, seconds: float) -> str:
        milliseconds = max(int(round(seconds * 1000)), 0)
        hours, remainder = divmod(milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, millis = divmod(remainder, 1000)
        return f'{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}'
