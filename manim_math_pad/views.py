"""Manim Math Pad — API Views."""
from __future__ import annotations

import json
import logging

from django.http import FileResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from .models import Animation, Message, Session, ZettelCluster
from .engine.scene_generator import SceneGenerator
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


def _chat_page_context(request) -> dict:
    path = request.path
    if path.endswith('/chat/'):
        api_base = path.removesuffix('chat/')
    elif path.endswith('/chat-ui/'):
        api_base = path.removesuffix('chat-ui/')
    else:
        api_base = '/api/manim/'
    return {'api_base': api_base}


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

        # Save user message
        Message.objects.create(session=session, role='user', content=content)

        # Generate response
        scene_gen = SceneGenerator(enable_llm=True, scene_model=body.get('scene_model'))
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

        response_parts = []

        # Generate animation if requested
        animation = None
        if wants_animation:
            generated = scene_gen.generate(content, context=session.context)
            animation = Animation.objects.create(
                session=session,
                concept=generated.concept,
                scene_code=generated.scene_code,
                status='pending',
                metadata={'source': generated.source, 'scene_name': generated.scene_name},
            )
            response_parts.append(
                f'Animation queued for: {generated.concept} (source: {generated.source})'
            )

        # Generate zettel cluster if requested
        zettel = None
        if wants_zettel:
            cluster = zettel_gen.generate(content, session_context=session.context)
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

        # Build assistant response
        if not response_parts:
            response_text = f'Received: "{content}". '
            if scene_gen._match_concept(content):
                response_text += 'This concept has a template animation. Say "animate" to see it.'
            else:
                response_text += 'Ask me to animate or create zettel notes for this concept.'
        else:
            response_text = '\n'.join(response_parts)

        # Save assistant message
        Message.objects.create(
            session=session,
            role='assistant',
            content=response_text,
        )

        # Update session context
        context = session.context
        concepts = context.get('concepts', [])
        concepts.append(content)
        context['concepts'] = concepts[-20:]  # Keep last 20
        session.context = context
        session.save()

        response_data = {
            'message': response_text,
            'session_uid': str(session.uid),
        }

        if animation:
            response_data['animation'] = {
                'uid': str(animation.uid),
                'concept': animation.concept,
                'status': animation.status,
            }

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

        scene_gen = SceneGenerator(enable_llm=True, scene_model=body.get('scene_model'))
        generated = scene_gen.generate(concept, context=session.context)

        animation = Animation.objects.create(
            session=session,
            concept=generated.concept,
            scene_code=generated.scene_code,
            status='pending',
            metadata={'source': generated.source, 'scene_name': generated.scene_name},
        )

        return JsonResponse({
            'uid': str(animation.uid),
            'concept': animation.concept,
            'status': animation.status,
            'scene_name': generated.scene_name,
            'source': generated.source,
        }, status=201)


@method_decorator(csrf_exempt, name='dispatch')
class AnimationStatusView(View):
    """Check animation status or download result."""

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
        cluster = zettel_gen.generate(topic, session_context=session.context)

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
