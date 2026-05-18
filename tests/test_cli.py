"""Tests for the Manim Math Pad CLI artifact contract."""
from __future__ import annotations

import json

from manim_math_pad.cli import main


def test_plan_lesson_writes_artifact_folder(tmp_path, capsys):
    out_dir = tmp_path / 'lesson'

    exit_code = main(
        [
            'plan-lesson',
            '--concept',
            'Explain derivative through limits',
            '--out',
            str(out_dir),
            '--lesson-id',
            'lesson-derivative',
        ]
    )

    assert exit_code == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest['ok'] is True
    assert manifest['lesson_id'] == 'lesson-derivative'
    assert manifest['clip_count'] >= 4
    assert (out_dir / 'lesson.json').exists()
    assert (out_dir / 'lesson.md').exists()
    assert (out_dir / 'storyboard.json').exists()
    assert (out_dir / 'captions.vtt').read_text(encoding='utf-8').startswith('WEBVTT')
    assert len(list((out_dir / 'clips').glob('*.py'))) == manifest['clip_count']

    lesson = json.loads((out_dir / 'lesson.json').read_text(encoding='utf-8'))
    assert lesson['schema_version'] == 1
    assert lesson['concept'] == 'derivative'
    assert lesson['lesson_plan']['learning_goal'].startswith('Understand a derivative')
    assert lesson['subtitles'][0]['start_seconds'] == 0


def test_plan_lesson_accepts_conversation_json(tmp_path, capsys):
    conversation = tmp_path / 'conversation.json'
    conversation.write_text(
        json.dumps(
            {
                'messages': [
                    {'role': 'user', 'content': 'Can we talk about limits first?'},
                    {'role': 'assistant', 'content': 'Yes.'},
                    {'role': 'user', 'content': 'Now explain Euler identity visually.'},
                ],
                'context': {'previous_concepts': ['limits']},
            }
        ),
        encoding='utf-8',
    )

    exit_code = main(
        [
            'plan-lesson',
            '--conversation',
            str(conversation),
            '--out',
            str(tmp_path / 'euler'),
            '--lesson-id',
            'lesson-euler',
        ]
    )

    assert exit_code == 0
    capsys.readouterr()
    lesson = json.loads((tmp_path / 'euler' / 'lesson.json').read_text(encoding='utf-8'))
    assert lesson['concept'] == 'euler identity'
    assert lesson['previous_concepts'] == ['limits']


def test_export_zettel_uses_lesson_json(tmp_path, capsys):
    out_dir = tmp_path / 'lesson'
    assert main(
        [
            'plan-lesson',
            '--concept',
            'matrix multiplication',
            '--out',
            str(out_dir),
            '--lesson-id',
            'lesson-matrix',
        ]
    ) == 0
    capsys.readouterr()

    exit_code = main(
        [
            'export-zettel',
            '--lesson',
            str(out_dir / 'lesson.json'),
            '--timestamp',
            '20260518000000',
        ]
    )

    assert exit_code == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest['ok'] is True
    assert manifest['note_count'] >= 4
    assert len(list((out_dir / 'zettel').glob('*.md'))) == manifest['note_count']
    assert (out_dir / 'zettel_manifest.json').exists()


def test_render_lesson_dry_run_reports_planned_clip_sources(tmp_path, capsys):
    out_dir = tmp_path / 'lesson'
    assert main(
        [
            'plan-lesson',
            '--concept',
            'fourier series',
            '--out',
            str(out_dir),
            '--lesson-id',
            'lesson-fourier',
        ]
    ) == 0
    capsys.readouterr()

    exit_code = main(
        [
            'render-lesson',
            '--lesson',
            str(out_dir / 'lesson.json'),
            '--dry-run',
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['dry_run'] is True
    assert payload['clip_count'] >= 4
    assert all(path.endswith('.py') for path in payload['planned_clip_paths'])
