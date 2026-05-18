"""Tests for the Manim Math Pad CLI artifact contract."""
from __future__ import annotations

import json

from manim_math_pad.cli import LESSON_SCHEMA_ID, LESSON_SCHEMA_PATH, SCHEMA_VERSION, main


def test_lesson_schema_is_packaged_and_matches_runtime_contract():
    schema = json.loads(LESSON_SCHEMA_PATH.read_text(encoding='utf-8'))

    assert schema['$id'] == LESSON_SCHEMA_ID
    assert schema['properties']['schema_version']['const'] == SCHEMA_VERSION
    assert 'teaching_spec' in schema['required']


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
    assert lesson['schema_version'] == SCHEMA_VERSION
    assert lesson['schema_id'] == LESSON_SCHEMA_ID
    assert lesson['concept'] == 'derivative'
    assert lesson['lesson_plan']['learning_goal'].startswith('Understand a derivative')
    assert lesson['teaching_spec']['diagnosis']['learner_question']
    assert lesson['teaching_spec']['visual_metaphor']
    assert lesson['teaching_spec']['clip_director_notes'][0]['visual_primitives']
    assert lesson['teaching_spec']['zettel_targets'][0]['type'] == 'central'
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


def test_validate_lesson_reports_contract_summary(tmp_path, capsys):
    out_dir = tmp_path / 'lesson'
    assert main(
        [
            'plan-lesson',
            '--concept',
            'derivative',
            '--out',
            str(out_dir),
            '--lesson-id',
            'lesson-validate',
        ]
    ) == 0
    capsys.readouterr()

    exit_code = main(['validate-lesson', '--lesson', str(out_dir / 'lesson.json')])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['ok'] is True
    assert payload['schema_version'] == SCHEMA_VERSION
    assert payload['schema_id'] == LESSON_SCHEMA_ID
    assert payload['clip_count'] >= 4


def test_validate_lesson_rejects_incomplete_artifact(tmp_path, capsys):
    broken = tmp_path / 'broken.json'
    broken.write_text(json.dumps({'schema_version': SCHEMA_VERSION}), encoding='utf-8')

    exit_code = main(['validate-lesson', '--lesson', str(broken)])

    assert exit_code == 2
    error = json.loads(capsys.readouterr().err)
    assert error['ok'] is False
    assert 'lesson validation failed' in error['error']


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
