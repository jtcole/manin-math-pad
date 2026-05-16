"""Smoke tests for Manim Math Pad Django endpoints."""
from __future__ import annotations

import io
import json
import zipfile

from django.test import Client, override_settings

from manim_math_pad.engine.renderer import RenderResult
from manim_math_pad.models import Animation, AnimationStoryboard, Session


def post_json(client: Client, path: str, payload: dict):
    return client.post(path, data=json.dumps(payload), content_type='application/json')


def test_session_creation_and_chat_answer(migrated_db):
    client = Client()

    response = post_json(client, '/api/manim/session/', {'title': 'Calculus'})
    assert response.status_code == 201
    session_uid = response.json()['uid']

    chat = post_json(
        client,
        '/api/manim/chat/',
        {
            'session_uid': session_uid,
            'message': 'What is a derivative?',
            'animate': False,
            'zettel': False,
        },
    )

    assert chat.status_code == 200
    payload = chat.json()
    assert not payload['message'].startswith('Received:')
    assert 'derivative' in payload['message'].lower()

    session = Session.objects.get(uid=session_uid)
    assert 'derivative' in session.context['current_concept']
    assert session.context['concepts']
    assert 'previous_concepts' in session.context

    detail = client.get(f'/api/manim/session/{session_uid}/')
    assert detail.status_code == 200
    messages = detail.json()['messages']
    assert [message['role'] for message in messages] == ['user', 'assistant']


def test_chat_can_queue_animation_and_create_zettel(migrated_db):
    client = Client()
    session_uid = post_json(client, '/api/manim/session/', {}).json()['uid']

    response = post_json(
        client,
        '/api/manim/chat/',
        {
            'session_uid': session_uid,
            'message': 'Explain matrix multiplication',
            'animate': True,
            'zettel': True,
            'enable_llm': False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['storyboard']['status'] == 'pending'
    assert payload['storyboard']['clip_count'] >= 4
    assert payload['storyboard']['metadata']['target_duration_seconds'] >= 70
    assert payload['storyboard']['clips'][0]['clip_index'] == 1
    assert payload['storyboard']['clips'][0]['target_duration_seconds'] >= 16
    assert payload['storyboard']['clips'][0]['learner_check']
    assert payload['animation']['status'] == 'pending'
    assert payload['animation']['storyboard_uid'] == payload['storyboard']['uid']
    assert payload['animation']['scene_code'].startswith('from manim import *')
    assert payload['zettel']['status'] == 'completed'
    assert payload['zettel']['note_count'] >= 4

    storyboard = AnimationStoryboard.objects.get(uid=payload['storyboard']['uid'])
    assert storyboard.clips.count() == payload['storyboard']['clip_count']


def test_storyboard_endpoint_queues_connected_clip_jobs(migrated_db):
    client = Client()
    session_uid = post_json(client, '/api/manim/session/', {}).json()['uid']

    response = post_json(
        client,
        '/api/manim/storyboard/',
        {
            'session_uid': session_uid,
            'concept': 'derivative',
            'clip_count': 4,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload['concept'] == 'derivative'
    assert payload['status'] == 'pending'
    assert payload['clip_count'] == 4
    assert payload['metadata']['lesson_plan']['learning_goal']
    assert payload['metadata']['target_duration_seconds'] >= 60
    assert [clip['clip_index'] for clip in payload['clips']] == [1, 2, 3, 4]
    assert all(clip['storyboard_uid'] == payload['uid'] for clip in payload['clips'])
    assert all(clip['target_duration_seconds'] >= 18 for clip in payload['clips'])

    detail = client.get(f'/api/manim/session/{session_uid}/')
    assert detail.status_code == 200
    assert detail.json()['storyboards'][0]['uid'] == payload['uid']


def test_storyboard_can_be_canceled_as_one_job(migrated_db):
    client = Client()
    session_uid = post_json(client, '/api/manim/session/', {}).json()['uid']
    storyboard = post_json(
        client,
        '/api/manim/storyboard/',
        {'session_uid': session_uid, 'concept': 'matrix multiplication'},
    ).json()

    response = client.patch(
        f'/api/manim/storyboard/{storyboard["uid"]}/',
        data=json.dumps({'status': 'canceled'}),
        content_type='application/json',
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'canceled'
    assert {clip['status'] for clip in payload['clips']} == {'canceled'}


def test_inline_animation_mode_marks_completed(migrated_db, monkeypatch, tmp_path):
    media_root = tmp_path / 'media'
    client = Client()
    session_uid = post_json(client, '/api/manim/session/', {}).json()['uid']

    def fake_render(self, scene_code, scene_name, job_uid=None, timeout=120):
        video_path = tmp_path / 'rendered.mp4'
        video_path.write_bytes(b'video')
        return RenderResult(
            success=True,
            video_path=video_path,
            metadata={'scene_name': scene_name, 'file_size_bytes': video_path.stat().st_size},
        )

    monkeypatch.setattr('manim_math_pad.views.ManimRenderer.render', fake_render)

    with override_settings(MEDIA_ROOT=str(media_root), MEDIA_URL='/media/'):
        response = post_json(
            client,
            '/api/manim/animate/',
            {
                'session_uid': session_uid,
                'concept': 'euler identity',
                'render_mode': 'inline',
                'quality': 'low_quality',
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload['status'] == 'completed'
    assert payload['video_url'].endswith('.mp4')

    animation = Animation.objects.get(uid=payload['uid'])
    assert animation.video_file.name.startswith('manim/animations/')


def test_zettel_endpoint_uses_conversation_concepts_for_connections(migrated_db):
    client = Client()
    session = Session.objects.create(
        title='Calculus',
        context={'concepts': ['derivatives', 'limits']},
    )

    response = post_json(
        client,
        '/api/manim/zettel/',
        {'session_uid': str(session.uid), 'topic': 'integrals'},
    )
    assert response.status_code == 201

    status = client.get(f'/api/manim/zettel/{response.json()["uid"]}/')
    assert status.status_code == 200
    notes = status.json()['notes']
    assert any(note.get('metadata', {}).get('type') == 'connection' for note in notes)
    assert all('_TODO' not in note['content'] for note in notes)


def test_zettel_export_endpoint_uses_configured_vault_path(migrated_db, tmp_path):
    client = Client()
    session_uid = post_json(client, '/api/manim/session/', {}).json()['uid']
    cluster_uid = post_json(
        client,
        '/api/manim/zettel/',
        {'session_uid': session_uid, 'topic': 'fourier series'},
    ).json()['uid']

    vault_path = tmp_path / 'vault'
    with override_settings(MANIM_VAULT_PATH=str(vault_path)):
        response = post_json(client, f'/api/manim/zettel/{cluster_uid}/export/', {})

    assert response.status_code == 200
    payload = response.json()
    assert payload['cluster_path'].startswith(str(vault_path))
    assert payload['created_paths']
    assert all(path.startswith(str(vault_path)) for path in payload['created_paths'])


def test_session_export_contains_transcript_scene_code_and_zettels(migrated_db):
    client = Client()
    session_uid = post_json(client, '/api/manim/session/', {'title': 'Export Demo'}).json()['uid']
    post_json(
        client,
        '/api/manim/chat/',
        {
            'session_uid': session_uid,
            'message': 'Explain euler identity',
            'animate': True,
            'zettel': True,
            'enable_llm': False,
        },
    )

    response = client.get(f'/api/manim/session/{session_uid}/export/')

    assert response.status_code == 200
    assert response['Content-Type'] == 'application/zip'

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(archive.namelist())
    assert 'transcript.md' in names
    assert any(name.startswith('manim/') and name.endswith('.py') for name in names)
    assert any(name.startswith('zettel/') and name.endswith('.md') for name in names)
