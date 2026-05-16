"""Manim Math Pad — API Views."""
from __future__ import annotations

import io
import json
import logging
import os
import re
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from .models import Animation, AnimationStoryboard, Message, Session, ZettelCluster
from .engine.chat_service import MathChatService
from .engine.renderer import ManimRenderer
from .engine.scene_generator import LLMSceneGenerator, SceneGenerator
from .engine.storyboard_generator import StoryboardGenerator
from .engine.vault_exporter import VaultZettelExporter
from .engine.zettel_generator import ZettelGenerator

logger = logging.getLogger(__name__)


def _json_body(request) -> dict:
    if not request.body:
        return {}
    return json.loads(request.body)


def _file_url(file_field) -> str | None:
    if not file_field:
        return None
    try:
        return file_field.url
    except Exception:
        return None


def _media_url_for_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    try:
        path = Path(path_value).resolve()
        media_root = Path(getattr(settings, 'MEDIA_ROOT', '') or '').resolve()
        relative = path.relative_to(media_root)
    except (OSError, ValueError):
        return None

    media_url = str(getattr(settings, 'MEDIA_URL', '/media/') or '/media/')
    if not media_url.endswith('/'):
        media_url += '/'
    return media_url + relative.as_posix()


def _chat_page_context(request) -> dict:
    path = request.path
    if path.endswith('/chat/'):
        api_base = path.removesuffix('chat/')
    elif path.endswith('/chat-ui/'):
        api_base = path.removesuffix('chat-ui/')
    else:
        api_base = '/api/manim/'
    return {'api_base': api_base}


def _env_or_setting(name: str, default=None):
    value = os.environ.get(name)
    if value is not None:
        return value
    return getattr(settings, name, default)


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'inline'}


def _scene_llm_enabled(body: dict) -> bool:
    if 'enable_llm' in body:
        return _truthy(body.get('enable_llm'))
    if 'use_llm' in body:
        return _truthy(body.get('use_llm'))

    configured = _env_or_setting('MANIM_ENABLE_LLM')
    if configured is not None:
        return _truthy(configured)

    return bool(
        body.get('scene_model')
        or _env_or_setting('OPENAI_API_KEY')
        or _env_or_setting('OLLAMA_HOST')
        or _env_or_setting('MANIM_SCENE_MODEL')
        # Backward compatibility for the pre-migration misspelling.
        or _env_or_setting('MANIN_SCENE_MODEL')
    )


def _render_mode(body: dict) -> str:
    return str(body.get('render_mode') or _env_or_setting('MANIM_RENDER_MODE', 'queue')).lower()


def _storyboard_requested(body: dict, default: bool = False) -> bool:
    for key in ['storyboard', 'multi_step', 'multi_clip']:
        if key in body:
            return _truthy(body.get(key))
    configured = _env_or_setting('MANIM_STORYBOARD_DEFAULT')
    if configured is not None:
        return _truthy(configured)
    return default


def _int_option(body: dict, key: str, default: int) -> int:
    try:
        return int(body.get(key, default))
    except (TypeError, ValueError):
        return default


def _int_config(name: str, default: int) -> int:
    try:
        return int(_env_or_setting(name, default))
    except (TypeError, ValueError):
        return default


def _slug(value: str, fallback: str = 'export') -> str:
    slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', value.lower()).strip('-')
    return slug[:80] or fallback


@method_decorator(csrf_exempt, name='dispatch')
class SessionView(View):
    """Create or retrieve a chat session."""

    def get(self, request):
        """List recent sessions."""
        sessions = Session.objects.order_by('-updated_at')[:20]
        data = [
            {
                'uid': str(s.uid),
                'title': s.title,
                'created_at': s.created_at.isoformat(),
                'updated_at': s.updated_at.isoformat(),
                'message_count': s.messages.count(),
            }
            for s in sessions
        ]
        return JsonResponse({'sessions': data})

    def post(self, request):
        """Create a new session."""
        body = _json_body(request)
        session = Session.objects.create(
            title=body.get('title', ''),
            context=body.get('context', {}),
        )
        return JsonResponse({
            'uid': str(session.uid),
            'title': session.title,
            'created_at': session.created_at.isoformat(),
        }, status=201)


@method_decorator(csrf_exempt, name='dispatch')
class SessionDetailView(View):
    """Retrieve one session with messages and generated artifacts."""

    def get(self, request, uid):
        try:
            session = Session.objects.get(uid=uid)
        except Session.DoesNotExist:
            return JsonResponse({'error': 'Session not found'}, status=404)

        return JsonResponse(
            {
                'uid': str(session.uid),
                'title': session.title,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'messages': [
                    {
                        'uid': str(message.uid),
                        'role': message.role,
                        'content': message.content,
                        'created_at': message.created_at.isoformat(),
                    }
                    for message in session.messages.order_by('created_at')
                ],
                'animations': [
                    _animation_payload(animation, include_urls=True)
                    for animation in session.animations.order_by('created_at')
                ],
                'storyboards': [
                    _storyboard_payload(storyboard, include_urls=True)
                    for storyboard in session.storyboards.order_by('created_at')
                ],
                'zettel_clusters': [
                    {
                        'uid': str(cluster.uid),
                        'topic': cluster.topic,
                        'status': cluster.status,
                        'note_count': cluster.note_count,
                        'created_at': cluster.created_at.isoformat(),
                        'notes': cluster.zettel_data.get('notes', []),
                    }
                    for cluster in session.zettel_clusters.order_by('created_at')
                ],
            }
        )


@method_decorator(csrf_exempt, name='dispatch')
class SessionExportView(View):
    """Export a session transcript, scene code, videos, and zettel notes."""

    def get(self, request, uid):
        try:
            session = Session.objects.get(uid=uid)
        except Session.DoesNotExist:
            return JsonResponse({'error': 'Session not found'}, status=404)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('transcript.md', _session_transcript(session))

            for animation in session.animations.order_by('created_at'):
                if animation.scene_code:
                    code_name = f'{animation.uid}_{_slug(animation.concept, "scene")}.py'
                    archive.writestr(f'manim/{code_name}', animation.scene_code)
                if animation.video_file:
                    try:
                        with animation.video_file.open('rb') as video_file:
                            extension = Path(animation.video_file.name).suffix or '.mp4'
                            archive.writestr(
                                f'figures/{animation.uid}{extension}',
                                video_file.read(),
                            )
                    except OSError:
                        logger.warning('Could not include video for animation %s', animation.uid)

            for storyboard in session.storyboards.order_by('created_at'):
                metadata = storyboard.metadata or {}
                combined_path = metadata.get('combined_video_path')
                if not combined_path:
                    continue
                try:
                    video_path = Path(combined_path)
                    if video_path.exists():
                        archive.writestr(
                            f'storyboards/{storyboard.uid}{video_path.suffix or ".mp4"}',
                            video_path.read_bytes(),
                        )
                except OSError:
                    logger.warning('Could not include storyboard video for %s', storyboard.uid)

            for cluster in session.zettel_clusters.filter(status='completed').order_by('created_at'):
                cluster_dir = f'zettel/{cluster.uid}'
                for note in cluster.zettel_data.get('notes', []):
                    filename = _slug(str(note.get('filename') or note.get('title')), 'note')
                    archive.writestr(
                        f'{cluster_dir}/{filename}.md',
                        str(note.get('content') or ''),
                    )

        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        filename = f'manim-math-pad-{_slug(session.title or str(session.uid), "session")}.zip'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


@method_decorator(csrf_exempt, name='dispatch')
class ChatPageView(View):
    """Serve the browser chat interface."""

    def get(self, request):
        return render(request, 'manim_math_pad/chat.html', _chat_page_context(request))


@method_decorator(csrf_exempt, name='dispatch')
class ChatView(View):
    """Send a message and receive a response."""

    def get(self, request):
        """Serve the chat page when accessed from a browser."""
        return render(request, 'manim_math_pad/chat.html', _chat_page_context(request))

    def post(self, request):
        """Send a message to the math pad and get a response."""
        body = _json_body(request)
        session_uid = body.get('session_uid')
        content = body.get('message', '').strip()

        if not session_uid or not content:
            return JsonResponse({'error': 'session_uid and message are required'}, status=400)

        try:
            session = Session.objects.get(uid=session_uid)
        except Session.DoesNotExist:
            return JsonResponse({'error': 'Session not found'}, status=404)

        Message.objects.create(session=session, role='user', content=content)

        chat_service = MathChatService(chat_model=body.get('model'))
        chat_turn = chat_service.respond(content, session.context)
        scene_gen = SceneGenerator(
            enable_llm=_scene_llm_enabled(body),
            scene_model=body.get('model') or body.get('scene_model'),
        )
        zettel_gen = ZettelGenerator()

        # Check if user wants an animation
        animate_flag = body.get('animate')
        zettel_flag = body.get('zettel')
        wants_animation = (
            bool(animate_flag)
            if animate_flag is not None
            else any(
                kw in content.lower()
                for kw in ['animate', 'show me', 'visualize', 'draw', 'render']
            )
        )
        wants_zettel = (
            bool(zettel_flag)
            if zettel_flag is not None
            else any(
                kw in content.lower()
                for kw in ['zettel', 'notes', 'cluster', 'obsidian', 'connect']
            )
        )

        response_parts = [chat_turn.answer]

        # Generate animation if requested
        animation = None
        storyboard = None
        if wants_animation:
            if _storyboard_requested(body, default=True):
                storyboard = _create_storyboard(
                    session=session,
                    concept=chat_turn.concept,
                    artifact_context=chat_turn.artifact_context,
                    body=body,
                )
                animation = storyboard.clips.order_by('clip_index', 'created_at').first()
                response_parts.append(
                    _artifact_status_sentence(
                        'Storyboard',
                        storyboard.status,
                        storyboard.concept,
                    )
                )
            else:
                generated = scene_gen.generate(chat_turn.concept, context=chat_turn.artifact_context)
                animation = Animation.objects.create(
                    session=session,
                    concept=generated.concept,
                    scene_code=generated.scene_code,
                    status='pending',
                    metadata={'source': generated.source, 'scene_name': generated.scene_name},
                )
                animation = _maybe_render_inline(animation, body)
                response_parts.append(
                    _artifact_status_sentence('Animation', animation.status, generated.concept)
                )

        # Generate zettel cluster if requested
        zettel = None
        if wants_zettel:
            cluster = zettel_gen.generate(
                chat_turn.concept,
                session_context=chat_turn.artifact_context,
            )
            zettel = ZettelCluster.objects.create(
                session=session,
                topic=cluster.topic,
                status='completed',
                zettel_data={
                    'notes': [
                        {
                            'title': n.title,
                            'filename': n.filename,
                            'content': n.content,
                            'tags': n.tags,
                            'links': n.links,
                            'metadata': n.metadata,
                        }
                        for n in cluster.notes
                    ],
                    'domain': cluster.domain,
                },
                note_count=len(cluster.notes),
                completed_at=timezone.now(),
            )
            response_parts.append(
                f'Zettel cluster created for: {cluster.topic} ({len(cluster.notes)} notes)'
            )

        response_text = '\n\n'.join(response_parts)

        # Save assistant message
        Message.objects.create(
            session=session,
            role='assistant',
            content=response_text,
        )

        session.context = chat_turn.context
        if not session.title:
            session.title = chat_turn.concept.title()[:255]
        session.save()

        response_data = {
            'message': response_text,
            'session_uid': str(session.uid),
        }

        if animation:
            response_data['animation'] = _animation_payload(animation, include_urls=True)

        if storyboard:
            response_data['storyboard'] = _storyboard_payload(storyboard, include_urls=True)

        if zettel:
            response_data['zettel'] = {
                'uid': str(zettel.uid),
                'topic': zettel.topic,
                'note_count': zettel.note_count,
                'status': zettel.status,
            }

        return JsonResponse(response_data)


@method_decorator(csrf_exempt, name='dispatch')
class AnimateView(View):
    """Generate a Manim animation for a concept."""

    def post(self, request):
        """Queue an animation generation."""
        body = _json_body(request)
        session_uid = body.get('session_uid')
        concept = body.get('concept', '').strip()

        if not session_uid or not concept:
            return JsonResponse({'error': 'session_uid and concept are required'}, status=400)

        try:
            session = Session.objects.get(uid=session_uid)
        except Session.DoesNotExist:
            return JsonResponse({'error': 'Session not found'}, status=404)

        artifact_context = MathChatService().artifact_context(session.context, concept)
        if _storyboard_requested(body, default=False):
            storyboard = _create_storyboard(
                session=session,
                concept=concept,
                artifact_context=artifact_context,
                body=body,
            )
            return JsonResponse(_storyboard_payload(storyboard, include_urls=True), status=201)

        scene_gen = SceneGenerator(
            enable_llm=_scene_llm_enabled(body),
            scene_model=body.get('model') or body.get('scene_model'),
        )
        generated = scene_gen.generate(concept, context=artifact_context)

        animation = Animation.objects.create(
            session=session,
            concept=generated.concept,
            scene_code=generated.scene_code,
            status='pending',
            metadata={'source': generated.source, 'scene_name': generated.scene_name},
        )
        animation = _maybe_render_inline(animation, body)

        return JsonResponse(_animation_payload(animation, include_urls=True), status=201)


@method_decorator(csrf_exempt, name='dispatch')
class AnimationStatusView(View):
    """Check animation status, download result, or cancel."""

    def get(self, request, uid):
        """Get animation status or download video."""
        try:
            animation = Animation.objects.get(uid=uid)
        except Animation.DoesNotExist:
            return JsonResponse({'error': 'Animation not found'}, status=404)

        if animation.status == 'completed' and animation.video_file:
            # Check if download requested
            if request.GET.get('download') == '1':
                return FileResponse(
                    animation.video_file.open('rb'),
                    as_attachment=True,
                    filename=f'manim_{animation.concept[:40]}.mp4',
                )

        data = _animation_payload(
            animation,
            include_urls=True,
            download_url=f'{request.path}?download=1',
        )

        if animation.error_message:
            data['error'] = animation.error_message

        return JsonResponse(data)

    def patch(self, request, uid):
        """Update an animation (e.g., cancel)."""
        body = _json_body(request)
        try:
            animation = Animation.objects.get(uid=uid)
        except Animation.DoesNotExist:
            return JsonResponse({'error': 'Animation not found'}, status=404)

        new_status = body.get('status')
        if new_status:
            if new_status not in ['pending', 'canceled']:
                return JsonResponse(
                    {'error': f'Cannot set status to "{new_status}"'}, status=400
                )
            animation.status = new_status
            if new_status == 'canceled':
                animation.error_message = 'Canceled by user'
                animation.completed_at = timezone.now()
            animation.save()
            if animation.storyboard_id:
                _sync_storyboard_status(animation.storyboard)

        return JsonResponse(_animation_payload(animation, include_urls=True))


@method_decorator(csrf_exempt, name='dispatch')
class StoryboardView(View):
    """Queue a multi-clip storyboard for a concept."""

    def post(self, request):
        body = _json_body(request)
        session_uid = body.get('session_uid')
        concept = body.get('concept', '').strip()

        if not session_uid or not concept:
            return JsonResponse({'error': 'session_uid and concept are required'}, status=400)

        try:
            session = Session.objects.get(uid=session_uid)
        except Session.DoesNotExist:
            return JsonResponse({'error': 'Session not found'}, status=404)

        artifact_context = MathChatService().artifact_context(session.context, concept)
        storyboard = _create_storyboard(
            session=session,
            concept=concept,
            artifact_context=artifact_context,
            body=body,
        )
        return JsonResponse(_storyboard_payload(storyboard, include_urls=True), status=201)


@method_decorator(csrf_exempt, name='dispatch')
class StoryboardStatusView(View):
    """Get or cancel a multi-clip storyboard."""

    def get(self, request, uid):
        try:
            storyboard = AnimationStoryboard.objects.get(uid=uid)
        except AnimationStoryboard.DoesNotExist:
            return JsonResponse({'error': 'Storyboard not found'}, status=404)

        return JsonResponse(_storyboard_payload(storyboard, include_urls=True))

    def patch(self, request, uid):
        body = _json_body(request)
        try:
            storyboard = AnimationStoryboard.objects.get(uid=uid)
        except AnimationStoryboard.DoesNotExist:
            return JsonResponse({'error': 'Storyboard not found'}, status=404)

        new_status = body.get('status')
        if new_status != 'canceled':
            return JsonResponse({'error': f'Cannot set status to "{new_status}"'}, status=400)

        _cancel_storyboard(storyboard)
        return JsonResponse(_storyboard_payload(storyboard, include_urls=True))


@method_decorator(csrf_exempt, name='dispatch')
class ZettelView(View):
    """Generate an Obsidian zettel cluster."""

    def post(self, request):
        """Queue a zettel cluster generation."""
        body = _json_body(request)
        session_uid = body.get('session_uid')
        topic = body.get('topic', '').strip()

        if not session_uid or not topic:
            return JsonResponse({'error': 'session_uid and topic are required'}, status=400)

        try:
            session = Session.objects.get(uid=session_uid)
        except Session.DoesNotExist:
            return JsonResponse({'error': 'Session not found'}, status=404)

        zettel_gen = ZettelGenerator()
        artifact_context = MathChatService().artifact_context(session.context, topic)
        cluster = zettel_gen.generate(topic, session_context=artifact_context)

        zettel = ZettelCluster.objects.create(
            session=session,
            topic=cluster.topic,
            status='completed',
            zettel_data={
                'notes': [
                    {
                        'title': n.title,
                        'filename': n.filename,
                        'content': n.content,
                        'tags': n.tags,
                        'links': n.links,
                        'metadata': n.metadata,
                    }
                    for n in cluster.notes
                ],
                'domain': cluster.domain,
            },
            note_count=len(cluster.notes),
            completed_at=timezone.now(),
        )

        return JsonResponse({
            'uid': str(zettel.uid),
            'topic': zettel.topic,
            'domain': cluster.domain,
            'note_count': zettel.note_count,
            'status': zettel.status,
            'notes': [
                {'title': n.title, 'filename': n.filename, 'tags': n.tags}
                for n in cluster.notes
            ],
        }, status=201)


@method_decorator(csrf_exempt, name='dispatch')
class ZettelStatusView(View):
    """Get zettel cluster details or download as zip."""

    def get(self, request, uid):
        """Get zettel cluster status or download."""
        try:
            zettel = ZettelCluster.objects.get(uid=uid)
        except ZettelCluster.DoesNotExist:
            return JsonResponse({'error': 'Zettel cluster not found'}, status=404)

        data = {
            'uid': str(zettel.uid),
            'topic': zettel.topic,
            'domain': zettel.zettel_data.get('domain', 'general'),
            'note_count': zettel.note_count,
            'status': zettel.status,
            'notes': zettel.zettel_data.get('notes', []),
        }

        if zettel.error_message:
            data['error'] = zettel.error_message

        return JsonResponse(data)


@method_decorator(csrf_exempt, name='dispatch')
class ZettelExportView(View):
    """Export a completed zettel cluster to the configured Obsidian vault."""

    def post(self, request, uid):
        """Write cluster notes as Markdown files."""
        try:
            zettel = ZettelCluster.objects.get(uid=uid)
        except ZettelCluster.DoesNotExist:
            return JsonResponse({'error': 'Zettel cluster not found'}, status=404)

        exporter = VaultZettelExporter()
        try:
            result = exporter.export_cluster(zettel)
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=400)

        data = result.as_json()
        data.update(
            {
                'uid': str(zettel.uid),
                'topic': zettel.topic,
                'status': zettel.status,
            }
        )
        return JsonResponse(data)


@method_decorator(csrf_exempt, name='dispatch')
class ZettelExportAllView(View):
    """Export all completed zettel clusters for one session."""

    def post(self, request):
        """Write all completed cluster notes for a session."""
        body = _json_body(request)
        session_uid = body.get('session_uid')
        if not session_uid:
            return JsonResponse({'error': 'session_uid is required'}, status=400)

        try:
            session = Session.objects.get(uid=session_uid)
        except Session.DoesNotExist:
            return JsonResponse({'error': 'Session not found'}, status=404)

        exporter = VaultZettelExporter()
        results = [
            exporter.export_cluster(cluster).as_json()
            for cluster in session.zettel_clusters.filter(status='completed').order_by('created_at')
        ]

        return JsonResponse(
            {
                'session_uid': str(session.uid),
                'cluster_count': len(results),
                'clusters': results,
                'created_paths': [
                    path
                    for result in results
                    for path in result.get('created_paths', [])
                ],
                'skipped_paths': [
                    path
                    for result in results
                    for path in result.get('skipped_paths', [])
                ],
            }
        )


def _artifact_status_sentence(kind: str, status: str, concept: str) -> str:
    if status == 'completed':
        return f'{kind} completed for: {concept}'
    if status == 'failed':
        return f'{kind} failed for: {concept}. Open the artifact details for the render error.'
    if status == 'rendering':
        return f'{kind} is rendering for: {concept}'
    return f'{kind} queued for: {concept}'


def _create_storyboard(
    session: Session,
    concept: str,
    artifact_context: dict,
    body: dict,
) -> AnimationStoryboard:
    max_clips = _int_option(body, 'clip_count', _int_config('MANIM_STORYBOARD_MAX_CLIPS', 5))
    target_clip_seconds = _int_option(
        body,
        'target_clip_seconds',
        _int_config('MANIM_STORYBOARD_CLIP_SECONDS', 18),
    )
    generated = StoryboardGenerator(
        max_clips=max_clips,
        target_clip_seconds=target_clip_seconds,
    ).generate(concept, context=artifact_context)
    storyboard = AnimationStoryboard.objects.create(
        session=session,
        concept=generated.concept,
        summary=generated.summary,
        status='pending',
        metadata={
            **generated.metadata,
            'domain': generated.domain,
            'model': body.get('model') or body.get('scene_model'),
        },
    )

    clip_count = len(generated.clips)
    for clip in generated.clips:
        animation = Animation.objects.create(
            session=session,
            storyboard=storyboard,
            concept=generated.concept,
            clip_index=clip.index,
            clip_count=clip_count,
            clip_title=clip.title,
            clip_summary=clip.narration,
            scene_code=clip.scene_code,
            status='pending',
            metadata={
                'source': 'pedagogical_storyboard',
                'scene_name': clip.scene_name,
                'storyboard_uid': str(storyboard.uid),
                'clip_index': clip.index,
                'clip_count': clip_count,
                'clip_title': clip.title,
                'clip_objective': clip.objective,
                'clip_purpose': clip.purpose,
                'visual_action': clip.visual_action,
                'math_focus': clip.math_focus,
                'learner_check': clip.learner_check,
                'target_duration_seconds': clip.duration_seconds,
                'generation': clip.metadata,
            },
        )
        _maybe_render_inline(animation, body)

    return _sync_storyboard_status(storyboard)


def _sync_storyboard_status(storyboard: AnimationStoryboard) -> AnimationStoryboard:
    clips = list(storyboard.clips.all())
    statuses = {clip.status for clip in clips}

    if not clips:
        status = 'pending'
    elif statuses <= {'completed'}:
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
    return storyboard


def _cancel_storyboard(storyboard: AnimationStoryboard) -> AnimationStoryboard:
    now = timezone.now()
    storyboard.clips.filter(status__in=['pending', 'generating', 'rendering']).update(
        status='canceled',
        error_message='Canceled by user',
        completed_at=now,
    )
    storyboard.status = 'canceled'
    storyboard.completed_at = now
    storyboard.save(update_fields=['status', 'completed_at'])
    return storyboard


def _storyboard_payload(storyboard: AnimationStoryboard, include_urls: bool = False) -> dict:
    storyboard = _sync_storyboard_status(storyboard)
    clips = list(storyboard.clips.order_by('clip_index', 'created_at'))
    metadata = storyboard.metadata or {}
    data = {
        'uid': str(storyboard.uid),
        'concept': storyboard.concept,
        'status': storyboard.status,
        'summary': storyboard.summary,
        'clip_count': len(clips),
        'created_at': storyboard.created_at.isoformat(),
        'completed_at': storyboard.completed_at.isoformat() if storyboard.completed_at else None,
        'metadata': metadata,
        'clips': [
            _animation_payload(clip, include_urls=include_urls)
            for clip in clips
        ],
    }
    if include_urls:
        combined_video_url = _media_url_for_path(metadata.get('combined_video_path'))
        combined_thumbnail_url = _media_url_for_path(metadata.get('combined_thumbnail_path'))
        if combined_video_url:
            data['combined_video_url'] = combined_video_url
            data['download_url'] = combined_video_url
        if combined_thumbnail_url:
            data['combined_thumbnail_url'] = combined_thumbnail_url
    if metadata.get('combined_duration_seconds') is not None:
        data['duration_seconds'] = metadata.get('combined_duration_seconds')
    if metadata.get('combined_status'):
        data['combined_status'] = metadata.get('combined_status')
    if metadata.get('combined_error'):
        data['combined_error'] = metadata.get('combined_error')
    return data


def _maybe_render_inline(animation: Animation, body: dict) -> Animation:
    """Render immediately when local/demo inline mode is enabled."""
    if _render_mode(body) not in {'inline', 'sync', 'immediate'}:
        return animation

    scene_name = (animation.metadata or {}).get('scene_name')
    if not scene_name:
        scene_name = LLMSceneGenerator.extract_scene_name(animation.scene_code)

    if not scene_name:
        animation.status = 'failed'
        animation.error_message = 'Could not determine Manim scene class name'
        animation.completed_at = timezone.now()
        animation.save(update_fields=['status', 'error_message', 'completed_at'])
        return animation

    metadata = animation.metadata or {}
    metadata['scene_name'] = scene_name
    metadata['render_mode'] = 'inline'
    animation.metadata = metadata
    animation.status = 'rendering'
    animation.error_message = ''
    animation.save(update_fields=['metadata', 'status', 'error_message'])

    renderer = ManimRenderer(
        output_dir=_inline_render_output_dir(),
        quality=str(body.get('quality') or _env_or_setting('MANIM_RENDER_QUALITY', 'low_quality')),
        fps=_int_option(body, 'fps', _int_config('MANIM_RENDER_FPS', 15)),
        manim_cmd=str(body.get('manim_cmd') or _env_or_setting('MANIM_CMD', 'manim')),
    )
    result = renderer.render(
        animation.scene_code,
        scene_name,
        job_uid=str(animation.uid),
        timeout=_int_option(body, 'timeout', _int_config('MANIM_RENDER_TIMEOUT', 120)),
    )

    metadata = animation.metadata or {}
    metadata.update(result.metadata or {})
    animation.metadata = metadata
    animation.completed_at = timezone.now()
    animation.duration_seconds = result.duration_seconds

    if not result.success:
        animation.status = 'failed'
        animation.error_message = (result.error_message or 'Unknown render failure')[:2000]
        animation.save(
            update_fields=[
                'metadata',
                'status',
                'error_message',
                'completed_at',
                'duration_seconds',
            ]
        )
        return animation

    animation.status = 'completed'
    animation.error_message = ''
    if result.video_path:
        with Path(result.video_path).open('rb') as video_file:
            animation.video_file.save(
                f'{animation.uid}.{Path(result.video_path).suffix.lstrip(".")}',
                File(video_file),
                save=False,
            )
    if result.thumbnail_path:
        with Path(result.thumbnail_path).open('rb') as thumbnail_file:
            animation.thumbnail_file.save(f'{animation.uid}.jpg', File(thumbnail_file), save=False)

    animation.save()
    return animation


def _inline_render_output_dir() -> Path:
    media_root = Path(getattr(settings, 'MEDIA_ROOT', '') or '/tmp/manim_math_pad_media')
    return media_root / 'manim' / 'inline_renders'


def _animation_payload(
    animation: Animation,
    include_urls: bool = False,
    download_url: str | None = None,
) -> dict:
    data = {
        'uid': str(animation.uid),
        'concept': animation.concept,
        'status': animation.status,
        'created_at': animation.created_at.isoformat(),
        'scene_name': (animation.metadata or {}).get('scene_name'),
        'source': (animation.metadata or {}).get('source'),
    }
    if animation.storyboard_id:
        metadata = animation.metadata or {}
        data.update(
            {
                'storyboard_uid': str(animation.storyboard.uid),
                'clip_index': animation.clip_index,
                'clip_count': animation.clip_count,
                'clip_title': animation.clip_title,
                'clip_summary': animation.clip_summary,
                'clip_purpose': metadata.get('clip_purpose'),
                'visual_action': metadata.get('visual_action'),
                'math_focus': metadata.get('math_focus'),
                'learner_check': metadata.get('learner_check'),
                'target_duration_seconds': metadata.get('target_duration_seconds'),
            }
        )

    if animation.scene_code:
        data['scene_code'] = animation.scene_code

    if animation.error_message:
        data['error'] = animation.error_message

    if animation.status == 'completed':
        data['duration_seconds'] = animation.duration_seconds
        data['download_url'] = download_url or f'/api/manim/animate/{animation.uid}/?download=1'

    if include_urls:
        video_url = _file_url(animation.video_file)
        thumbnail_url = _file_url(animation.thumbnail_file)
        if video_url:
            data['video_url'] = video_url
        if thumbnail_url:
            data['thumbnail_url'] = thumbnail_url

    return data


def _session_transcript(session: Session) -> str:
    """Render a session transcript with artifact references."""
    title = session.title or f'Session {session.uid}'
    lines = [
        f'# {title}',
        '',
        f'- Session: {session.uid}',
        f'- Created: {session.created_at.isoformat()}',
        f'- Updated: {session.updated_at.isoformat()}',
        '',
        '## Transcript',
        '',
    ]

    for message in session.messages.order_by('created_at'):
        lines.extend(
            [
                f'### {message.role.title()}',
                '',
                message.content,
                '',
            ]
        )

    storyboards = list(session.storyboards.order_by('created_at').prefetch_related('clips'))
    if storyboards:
        lines.extend(['## Storyboards', ''])
        for storyboard in storyboards:
            lines.extend(
                [
                    f'- {storyboard.concept} ({storyboard.status})',
                    f'  - UID: {storyboard.uid}',
                    f'  - Clips: {storyboard.clips.count()}',
                ]
            )
            for clip in storyboard.clips.order_by('clip_index', 'created_at'):
                title = clip.clip_title or clip.concept
                lines.append(f'  - Clip {clip.clip_index}: {title} ({clip.status})')
        lines.append('')

    animations = list(session.animations.filter(storyboard__isnull=True).order_by('created_at'))
    if animations:
        lines.extend(['## Manim Scenes', ''])
        for animation in animations:
            lines.extend(
                [
                    f'- {animation.concept} ({animation.status})',
                    f'  - UID: {animation.uid}',
                    f'  - Scene: {(animation.metadata or {}).get("scene_name") or "unknown"}',
                ]
            )
            if animation.video_file:
                lines.append(f'  - Video: figures/{animation.uid}{Path(animation.video_file.name).suffix}')
        lines.append('')

    clusters = list(session.zettel_clusters.filter(status='completed').order_by('created_at'))
    if clusters:
        lines.extend(['## Zettel Clusters', ''])
        for cluster in clusters:
            lines.append(f'- {cluster.topic}: {cluster.note_count} notes ({cluster.uid})')
        lines.append('')

    return '\n'.join(lines).rstrip() + '\n'
