"""CLI entrypoints for Manim Math Pad artifact workflows."""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .engine.renderer import ManimRenderer
from .engine.storyboard_generator import GeneratedStoryboard, StoryboardClip, StoryboardGenerator
from .engine.zettel_generator import ZettelGenerator


SCHEMA_VERSION = 2
LESSON_SCHEMA_ID = 'https://codingenvironment.com/schemas/manim-math-pad/lesson.v2.json'
LESSON_SCHEMA_PATH = Path(__file__).resolve().parent / 'schemas' / 'lesson.schema.json'


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == 'plan-lesson':
            result = plan_lesson_command(args)
        elif args.command == 'export-zettel':
            result = export_zettel_command(args)
        elif args.command == 'render-lesson':
            result = render_lesson_command(args)
        elif args.command == 'validate-lesson':
            result = validate_lesson_command(args)
        else:
            parser.error('a command is required')
            return 2
    except CliError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, indent=2), file=sys.stderr)
        return exc.exit_code

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='manim-pad',
        description='Create Manim lesson artifacts from conversations.',
    )
    subparsers = parser.add_subparsers(dest='command')

    plan = subparsers.add_parser(
        'plan-lesson',
        help='Create lesson.json, lesson.md, storyboard.json, captions, and clip source files.',
    )
    plan.add_argument('--concept', help='Concept or prompt to plan from.')
    plan.add_argument('--conversation', type=Path, help='JSON conversation file.')
    plan.add_argument('--out', type=Path, required=True, help='Output artifact directory.')
    plan.add_argument('--lesson-id', help='Stable lesson id. Defaults to a timestamped slug.')
    plan.add_argument('--max-clips', type=int, default=5)
    plan.add_argument('--target-clip-seconds', type=int, default=18)
    plan.add_argument('--overwrite', action='store_true')

    zettel = subparsers.add_parser(
        'export-zettel',
        help='Export zettel markdown files from a planned lesson.',
    )
    zettel.add_argument('--lesson', type=Path, required=True, help='Path to lesson.json.')
    zettel.add_argument('--out', type=Path, help='Artifact directory. Defaults to lesson parent.')
    zettel.add_argument('--timestamp', help='Timestamp prefix for zettel filenames.')
    zettel.add_argument('--overwrite', action='store_true')

    render = subparsers.add_parser(
        'render-lesson',
        help='Render lesson clips with Manim and assemble one video.',
    )
    render.add_argument('--lesson', type=Path, required=True, help='Path to lesson.json.')
    render.add_argument('--out', type=Path, help='Artifact directory. Defaults to lesson parent.')
    render.add_argument('--quality', default='low_quality')
    render.add_argument('--fps', type=int, default=15)
    render.add_argument('--timeout', type=int, default=240)
    render.add_argument('--manim-cmd', default='manim')
    render.add_argument('--dry-run', action='store_true')

    validate = subparsers.add_parser(
        'validate-lesson',
        help='Validate lesson.json against the MCP-ready lesson contract.',
    )
    validate.add_argument('--lesson', type=Path, required=True, help='Path to lesson.json.')

    return parser


def plan_lesson_command(args: argparse.Namespace) -> dict[str, Any]:
    conversation = _load_conversation(args.conversation) if args.conversation else None
    concept = _concept_from_inputs(args.concept, conversation)
    context = _context_from_conversation(conversation)
    storyboard = StoryboardGenerator(
        max_clips=args.max_clips,
        target_clip_seconds=args.target_clip_seconds,
    ).generate(concept, context=context)
    lesson_id = args.lesson_id or _lesson_id(storyboard.concept)
    payload = _lesson_payload(storyboard, lesson_id, conversation)
    return write_lesson_artifacts(payload, args.out, overwrite=args.overwrite)


def export_zettel_command(args: argparse.Namespace) -> dict[str, Any]:
    lesson = _load_lesson(args.lesson)
    out_dir = args.out or args.lesson.parent
    zettel_dir = out_dir / 'zettel'
    zettel_dir.mkdir(parents=True, exist_ok=True)

    timestamp = args.timestamp or _timestamp_from_lesson(lesson)
    context = {'previous_concepts': lesson.get('previous_concepts', [])}
    cluster = ZettelGenerator(timestamp=timestamp).generate(
        lesson['concept'],
        session_context=context,
    )

    created_paths: list[str] = []
    skipped_paths: list[str] = []
    for note in cluster.notes:
        path = zettel_dir / f'{note.filename}.md'
        if path.exists() and not args.overwrite:
            skipped_paths.append(str(path))
            continue
        path.write_text(note.content, encoding='utf-8')
        created_paths.append(str(path))

    manifest = {
        'ok': True,
        'command': 'export-zettel',
        'lesson_id': lesson['lesson_id'],
        'concept': lesson['concept'],
        'domain': cluster.domain,
        'zettel_dir': str(zettel_dir),
        'note_count': len(cluster.notes),
        'created_paths': created_paths,
        'skipped_paths': skipped_paths,
    }
    _write_json(out_dir / 'zettel_manifest.json', manifest)
    return manifest


def render_lesson_command(args: argparse.Namespace) -> dict[str, Any]:
    lesson = _load_lesson(args.lesson)
    out_dir = args.out or args.lesson.parent
    clip_dir = out_dir / 'clips'
    rendered_dir = out_dir / 'rendered_clips'
    rendered_dir.mkdir(parents=True, exist_ok=True)

    clips = lesson.get('clips') or []
    if args.dry_run:
        return {
            'ok': True,
            'command': 'render-lesson',
            'dry_run': True,
            'lesson_id': lesson['lesson_id'],
            'concept': lesson['concept'],
            'clip_count': len(clips),
            'planned_clip_paths': [
                str(clip_dir / f'{clip["index"]:02d}_{_slugify(clip["title"])}.py')
                for clip in clips
            ],
        }

    renderer = ManimRenderer(
        output_dir=rendered_dir,
        quality=args.quality,
        fps=args.fps,
        manim_cmd=args.manim_cmd,
    )
    rendered_paths: list[Path] = []
    for clip in clips:
        result = renderer.render(
            clip['scene_code'],
            clip['scene_name'],
            job_uid=f'{lesson["lesson_id"]}_{clip["index"]:02d}',
            timeout=args.timeout,
        )
        if not result.success or not result.video_path:
            raise CliError(
                f'clip {clip["index"]} failed to render: {result.error_message}',
                exit_code=1,
            )
        rendered_paths.append(result.video_path)

    combined_path = out_dir / 'video.mp4'
    thumbnail_path = out_dir / 'thumbnail.jpg'
    combined = renderer.concatenate_videos(
        rendered_paths,
        combined_path,
        thumbnail_path=thumbnail_path,
        timeout=args.timeout,
    )
    if not combined.success:
        raise CliError(f'failed to assemble lesson video: {combined.error_message}', exit_code=1)

    manifest = {
        'ok': True,
        'command': 'render-lesson',
        'lesson_id': lesson['lesson_id'],
        'concept': lesson['concept'],
        'clip_count': len(rendered_paths),
        'clip_video_paths': [str(path) for path in rendered_paths],
        'video_path': str(combined_path),
        'thumbnail_path': str(thumbnail_path) if thumbnail_path.exists() else None,
        'duration_seconds': combined.duration_seconds,
    }
    _write_json(out_dir / 'render_manifest.json', manifest)
    return manifest


def validate_lesson_command(args: argparse.Namespace) -> dict[str, Any]:
    lesson = _load_lesson(args.lesson)
    return {
        'ok': True,
        'command': 'validate-lesson',
        'lesson_id': lesson['lesson_id'],
        'concept': lesson['concept'],
        'schema_version': lesson['schema_version'],
        'schema_id': lesson['schema_id'],
        'clip_count': len(lesson['clips']),
        'target_duration_seconds': lesson['target_duration_seconds'],
    }


def write_lesson_artifacts(
    lesson: dict[str, Any],
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Write a planned lesson artifact folder and return a manifest."""
    _raise_for_lesson_errors(lesson)
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise CliError(f'output directory is not empty: {out_dir}')
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_dir = out_dir / 'clips'
    asset_dir = out_dir / 'assets'
    clip_dir.mkdir(exist_ok=True)
    asset_dir.mkdir(exist_ok=True)

    lesson_path = out_dir / 'lesson.json'
    storyboard_path = out_dir / 'storyboard.json'
    markdown_path = out_dir / 'lesson.md'
    captions_path = out_dir / 'captions.vtt'
    manifest_path = out_dir / 'artifact_manifest.json'

    _write_json(lesson_path, lesson)
    _write_json(storyboard_path, _storyboard_payload_for_file(lesson))
    markdown_path.write_text(_lesson_markdown(lesson), encoding='utf-8')
    captions_path.write_text(_captions_vtt(lesson), encoding='utf-8')

    clip_paths = []
    for clip in lesson['clips']:
        clip_path = clip_dir / f'{clip["index"]:02d}_{_slugify(clip["title"])}.py'
        clip_path.write_text(clip['scene_code'], encoding='utf-8')
        clip_paths.append(str(clip_path))

    manifest = {
        'ok': True,
        'command': 'plan-lesson',
        'schema_version': lesson['schema_version'],
        'schema_id': lesson['schema_id'],
        'lesson_id': lesson['lesson_id'],
        'concept': lesson['concept'],
        'domain': lesson['domain'],
        'target_duration_seconds': lesson['target_duration_seconds'],
        'clip_count': len(lesson['clips']),
        'lesson_path': str(lesson_path),
        'markdown_path': str(markdown_path),
        'storyboard_path': str(storyboard_path),
        'captions_path': str(captions_path),
        'clip_paths': clip_paths,
        'manifest_path': str(manifest_path),
    }
    _write_json(manifest_path, manifest)
    return manifest


def _lesson_payload(
    storyboard: GeneratedStoryboard,
    lesson_id: str,
    conversation: dict[str, Any] | list[Any] | None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    clips = []
    for clip in storyboard.clips:
        clips.append(
            {
                'index': clip.index,
                'title': clip.title,
                'objective': clip.objective,
                'narration': clip.narration,
                'scene_name': clip.scene_name,
                'scene_code': clip.scene_code,
                'duration_seconds': clip.duration_seconds,
                'purpose': clip.purpose,
                'visual_action': clip.visual_action,
                'math_focus': clip.math_focus,
                'learner_check': clip.learner_check,
                'metadata': clip.metadata,
            }
        )
    subtitles = []
    cursor = 0
    for clip in clips:
        start = cursor
        end = start + int(clip['duration_seconds'])
        subtitles.append(
            {
                'index': clip['index'],
                'start_seconds': start,
                'end_seconds': end,
                'text': clip['narration'],
            }
        )
        cursor = end

    return {
        'schema_version': SCHEMA_VERSION,
        'schema_id': LESSON_SCHEMA_ID,
        'schema_path': str(LESSON_SCHEMA_PATH),
        'lesson_id': lesson_id,
        'generated_at': generated_at,
        'concept': storyboard.concept,
        'domain': storyboard.domain,
        'summary': storyboard.summary,
        'target_duration_seconds': storyboard.target_duration_seconds,
        'lesson_plan': asdict(storyboard.lesson_plan),
        'teaching_spec': _teaching_spec(storyboard),
        'beats': [asdict(beat) for beat in storyboard.beats],
        'clips': clips,
        'subtitles': subtitles,
        'previous_concepts': storyboard.metadata.get('previous_concepts', []),
        'conversation': conversation,
        'metadata': storyboard.metadata,
    }


def _storyboard_payload_for_file(lesson: dict[str, Any]) -> dict[str, Any]:
    return {
        'schema_version': lesson['schema_version'],
        'schema_id': lesson['schema_id'],
        'lesson_id': lesson['lesson_id'],
        'concept': lesson['concept'],
        'domain': lesson['domain'],
        'summary': lesson['summary'],
        'target_duration_seconds': lesson['target_duration_seconds'],
        'lesson_plan': lesson['lesson_plan'],
        'teaching_spec': lesson['teaching_spec'],
        'beats': lesson['beats'],
        'clips': [
            {
                key: value
                for key, value in clip.items()
                if key not in {'scene_code'}
            }
            for clip in lesson['clips']
        ],
        'subtitles': lesson['subtitles'],
    }


def _lesson_markdown(lesson: dict[str, Any]) -> str:
    plan = lesson['lesson_plan']
    teaching = lesson['teaching_spec']
    lines = [
        f'# {lesson["concept"].title()}',
        '',
        lesson['summary'],
        '',
        '## Learning Goal',
        '',
        plan['learning_goal'],
        '',
        '## Teaching Diagnosis',
        '',
        f'- Learner question: {teaching["diagnosis"]["learner_question"]}',
        f'- Assumed gap: {teaching["diagnosis"]["assumed_gap"]}',
        f'- Target shift: {teaching["diagnosis"]["target_shift"]}',
        f'- Visual metaphor: {teaching["visual_metaphor"]}',
        '',
        '## Prerequisites',
        '',
        *[f'- {item}' for item in plan['prerequisites']],
        '',
        '## Misconception To Guard Against',
        '',
        plan['misconception'],
        '',
        '## Example',
        '',
        plan['example'],
        '',
        '## Takeaway',
        '',
        plan['takeaway'],
        '',
        '## Storyboard',
        '',
    ]
    for clip in lesson['clips']:
        director = teaching['clip_director_notes'][clip['index'] - 1]
        lines.extend(
            [
                f'### {clip["index"]}. {clip["title"]}',
                '',
                f'- Duration: {clip["duration_seconds"]} seconds',
                f'- Purpose: {clip["purpose"]}',
                f'- Visual action: {clip["visual_action"]}',
                f'- Math focus: {clip["math_focus"]}',
                f'- Learner check: {clip["learner_check"]}',
                f'- Subtitle: {director["subtitle"]}',
                f'- Visual primitives: {", ".join(director["visual_primitives"])}',
                f'- Animation actions: {", ".join(director["animation_actions"])}',
                '',
                clip['narration'],
                '',
            ]
        )
    return '\n'.join(lines).rstrip() + '\n'


def _teaching_spec(storyboard: GeneratedStoryboard) -> dict[str, Any]:
    """Create the bot/MCP-facing teaching spec from the planned storyboard."""
    plan = storyboard.lesson_plan
    return {
        'diagnosis': {
            'learner_question': f'What does {storyboard.concept} mean visually?',
            'assumed_gap': _assumed_gap(storyboard.domain),
            'misconception_to_surface': plan.misconception,
            'target_shift': (
                'Move the learner from symbol-recognition to a checkable visual model.'
            ),
        },
        'visual_metaphor': _visual_metaphor(storyboard.concept, storyboard.domain),
        'explainer_style': {
            'inspiration': '3Blue1Brown-style geometric explainer',
            'rules': [
                'Introduce one object at a time.',
                'Animate the mathematical action before naming the formula.',
                'Keep equations close to the object they describe.',
                'Use subtitles as narration, not as decorative labels.',
                'End each clip with one checkable question.',
            ],
        },
        'narrative_arc': [
            'Anchor the object.',
            'Animate the operation.',
            'Expose the invariant or limiting relationship.',
            'Work one small example.',
            'Name the reusable takeaway.',
        ],
        'zettel_targets': _zettel_targets(storyboard.concept, storyboard.domain),
        'clip_director_notes': [
            _clip_director_note(storyboard.domain, storyboard.concept, clip)
            for clip in storyboard.clips
        ],
        'artifact_contract': {
            'lesson_markdown': 'lesson.md',
            'lesson_json': 'lesson.json',
            'storyboard_json': 'storyboard.json',
            'captions': 'captions.vtt',
            'clip_sources': 'clips/*.py',
            'rendered_video': 'video.mp4',
            'zettel_notes': 'zettel/*.md',
        },
    }


def _assumed_gap(domain: str) -> str:
    gaps = {
        'calculus': 'The learner may know the formula but not the changing quantity.',
        'linear_algebra': 'The learner may see arrays of numbers but not transformations.',
        'complex_analysis': 'The learner may treat complex exponentials as symbolic tricks.',
        'general': 'The learner may not yet know the object, operation, and invariant.',
    }
    return gaps.get(domain, gaps['general'])


def _visual_metaphor(concept: str, domain: str) -> str:
    lowered = concept.lower()
    if 'derivative' in lowered:
        return 'A secant line turning into a local speedometer for a curve.'
    if 'limit' in lowered:
        return 'Nearby points squeezing the output toward one forced value.'
    if 'matrix' in lowered:
        return 'Rows asking columns for weighted totals, one output cell at a time.'
    if 'euler' in lowered:
        return 'A point walking around the unit circle until a half-turn lands on -1.'
    if 'fourier' in lowered:
        return 'Simple rotating waves stacking into a complicated repeating shape.'
    domain_metaphors = {
        'linear_algebra': 'A transformation made visible by watching objects move together.',
        'calculus': 'A changing quantity slowed down until the local rule becomes visible.',
        'complex_analysis': 'Motion in the plane tracked by coordinates and angle.',
    }
    return domain_metaphors.get(domain, 'A named object, a visible action, and a stable takeaway.')


def _zettel_targets(concept: str, domain: str) -> list[dict[str, str]]:
    topic = concept.title()
    return [
        {
            'title': topic,
            'type': 'central',
            'purpose': 'Define the concept and preserve the core visual insight.',
        },
        {
            'title': f'{topic} Visual Model',
            'type': 'atomic',
            'purpose': 'Capture the geometric or procedural metaphor used in the lesson.',
        },
        {
            'title': f'{topic} Common Misconception',
            'type': 'atomic',
            'purpose': 'Record the error the lesson is designed to prevent.',
        },
        {
            'title': f'{topic} Worked Example',
            'type': 'atomic',
            'purpose': 'Keep a small hand-checkable computation linked to the animation.',
        },
        {
            'title': f'{topic} Connections',
            'type': 'connection',
            'purpose': f'Connect this {domain.replace("_", " ")} lesson to nearby concepts.',
        },
    ]


def _clip_director_note(domain: str, concept: str, clip: StoryboardClip) -> dict[str, Any]:
    return {
        'clip_index': clip.index,
        'title': clip.title,
        'subtitle': clip.narration,
        'voiceover': clip.narration,
        'visual_primitives': _visual_primitives(domain, concept, clip),
        'animation_actions': _animation_actions(clip),
        'composition_notes': (
            'Use a stable header, leave equations in a fixed lower band, and keep the main '
            'mathematical object centered with no overlapping text.'
        ),
        'asset_needs': _asset_needs(domain, concept),
        'zettel_targets': [
            concept.title(),
            f'{concept.title()} Visual Model',
            f'{concept.title()} Worked Example',
        ],
        'code_entrypoint': clip.scene_name,
    }


def _visual_primitives(domain: str, concept: str, clip: StoryboardClip) -> list[str]:
    lowered = concept.lower()
    if 'derivative' in lowered:
        return ['axes', 'curve', 'two points', 'secant line', 'tangent line', 'slope label']
    if 'matrix' in lowered:
        return ['matrix A', 'matrix B', 'result matrix', 'row highlight', 'column highlight']
    if 'euler' in lowered:
        return ['complex plane', 'unit circle', 'rotating point', 'angle arc', 'coordinate labels']
    if 'fourier' in lowered:
        return ['target wave', 'component waves', 'summed waveform', 'frequency labels']
    if domain == 'linear_algebra':
        return ['basis grid', 'input vector', 'transformed vector', 'invariant label']
    if domain == 'calculus':
        return ['axes', 'function path', 'moving sample point', 'limit marker']
    return ['main object', 'operation arrow', 'invariant highlight', 'takeaway label']


def _animation_actions(clip: StoryboardClip) -> list[str]:
    return [
        'fade in the object before text',
        clip.visual_action,
        'highlight the math focus while narrating the subtitle',
        'pause on the learner check',
    ]


def _asset_needs(domain: str, concept: str) -> list[str]:
    lowered = concept.lower()
    if 'fourier' in lowered:
        return ['optional waveform audio/image reference for future richer renders']
    if domain == 'general':
        return ['optional domain-specific icon or sprite if the concept needs context']
    return []


def _captions_vtt(lesson: dict[str, Any]) -> str:
    lines = ['WEBVTT', '']
    for subtitle in lesson['subtitles']:
        lines.extend(
            [
                str(subtitle['index']),
                (
                    f'{_vtt_time(subtitle["start_seconds"])} --> '
                    f'{_vtt_time(subtitle["end_seconds"])}'
                ),
                subtitle['text'],
                '',
            ]
        )
    return '\n'.join(lines)


def _vtt_time(seconds: int | float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{secs:02d}.000'


def _concept_from_inputs(
    concept: str | None,
    conversation: dict[str, Any] | list[Any] | None,
) -> str:
    if concept and concept.strip():
        return concept.strip()
    if conversation is None:
        raise CliError('--concept or --conversation is required', exit_code=2)
    if isinstance(conversation, dict):
        explicit = conversation.get('concept') or conversation.get('topic')
        if explicit:
            return str(explicit).strip()
        messages = conversation.get('messages')
        transcript = conversation.get('transcript')
    else:
        messages = conversation
        transcript = None
    if isinstance(messages, list):
        user_messages = [
            str(item.get('content', '')).strip()
            for item in messages
            if isinstance(item, dict)
            and item.get('role', 'user') == 'user'
            and str(item.get('content', '')).strip()
        ]
        if user_messages:
            return user_messages[-1]
    if transcript:
        return str(transcript).strip()
    raise CliError('conversation did not contain a concept, transcript, or user messages')


def _context_from_conversation(conversation: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    if not isinstance(conversation, dict):
        return {}
    context = conversation.get('context')
    if isinstance(context, dict):
        return context
    previous = conversation.get('previous_concepts')
    if isinstance(previous, list):
        return {'previous_concepts': previous}
    return {}


def _load_conversation(path: Path) -> dict[str, Any] | list[Any]:
    if not path.exists():
        raise CliError(f'conversation file does not exist: {path}', exit_code=2)
    return _load_json(path)


def _load_lesson(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise CliError(f'lesson file must contain a JSON object: {path}', exit_code=2)
    _raise_for_lesson_errors(payload)
    return payload


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise CliError(f'invalid JSON in {path}: {exc}', exit_code=2) from exc


def _raise_for_lesson_errors(lesson: dict[str, Any]) -> None:
    errors = validate_lesson_payload(lesson)
    if errors:
        raise CliError('lesson validation failed: ' + '; '.join(errors), exit_code=2)


def validate_lesson_payload(lesson: dict[str, Any]) -> list[str]:
    """Validate the lesson artifact contract without adding a runtime dependency."""
    errors: list[str] = []
    required = {
        'schema_version': int,
        'schema_id': str,
        'lesson_id': str,
        'generated_at': str,
        'concept': str,
        'domain': str,
        'summary': str,
        'target_duration_seconds': int,
        'lesson_plan': dict,
        'teaching_spec': dict,
        'beats': list,
        'clips': list,
        'subtitles': list,
        'previous_concepts': list,
        'metadata': dict,
    }
    for field, expected_type in required.items():
        if field not in lesson:
            errors.append(f'missing field: {field}')
            continue
        if not isinstance(lesson[field], expected_type):
            errors.append(f'{field} must be {expected_type.__name__}')

    if errors:
        return errors

    if lesson['schema_version'] != SCHEMA_VERSION:
        errors.append(f'schema_version must be {SCHEMA_VERSION}')
    if lesson['schema_id'] != LESSON_SCHEMA_ID:
        errors.append(f'schema_id must be {LESSON_SCHEMA_ID}')
    if lesson['target_duration_seconds'] <= 0:
        errors.append('target_duration_seconds must be positive')

    plan_required = [
        'concept',
        'audience_level',
        'learning_goal',
        'prerequisites',
        'misconception',
        'example',
        'takeaway',
    ]
    for field in plan_required:
        if field not in lesson['lesson_plan']:
            errors.append(f'lesson_plan missing field: {field}')

    teaching = lesson['teaching_spec']
    for field in [
        'diagnosis',
        'visual_metaphor',
        'explainer_style',
        'narrative_arc',
        'zettel_targets',
        'clip_director_notes',
        'artifact_contract',
    ]:
        if field not in teaching:
            errors.append(f'teaching_spec missing field: {field}')

    clips = lesson['clips']
    subtitles = lesson['subtitles']
    director_notes = teaching.get('clip_director_notes', [])
    if not clips:
        errors.append('clips must not be empty')
    if len(subtitles) != len(clips):
        errors.append('subtitles length must match clips length')
    if isinstance(director_notes, list) and len(director_notes) != len(clips):
        errors.append('clip_director_notes length must match clips length')

    total_duration = 0
    for expected_index, clip in enumerate(clips, start=1):
        if not isinstance(clip, dict):
            errors.append(f'clip {expected_index} must be object')
            continue
        for field in [
            'index',
            'title',
            'objective',
            'narration',
            'scene_name',
            'scene_code',
            'duration_seconds',
            'purpose',
            'visual_action',
            'math_focus',
            'learner_check',
            'metadata',
        ]:
            if field not in clip:
                errors.append(f'clip {expected_index} missing field: {field}')
        if clip.get('index') != expected_index:
            errors.append(f'clip {expected_index} index is not sequential')
        duration = clip.get('duration_seconds')
        if not isinstance(duration, int) or duration <= 0:
            errors.append(f'clip {expected_index} duration_seconds must be positive integer')
        else:
            total_duration += duration
        scene_code = str(clip.get('scene_code', ''))
        if 'class ' not in scene_code or 'construct(self)' not in scene_code:
            errors.append(f'clip {expected_index} scene_code must define a Manim Scene')

    if total_duration and total_duration != lesson['target_duration_seconds']:
        errors.append('target_duration_seconds must equal sum of clip durations')

    for expected_index, subtitle in enumerate(subtitles, start=1):
        if not isinstance(subtitle, dict):
            errors.append(f'subtitle {expected_index} must be object')
            continue
        if subtitle.get('index') != expected_index:
            errors.append(f'subtitle {expected_index} index is not sequential')
        if not str(subtitle.get('text', '')).strip():
            errors.append(f'subtitle {expected_index} text must not be empty')

    return errors


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _lesson_id(concept: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    return f'{timestamp}_{_slugify(concept)}'


def _timestamp_from_lesson(lesson: dict[str, Any]) -> str:
    generated_at = str(lesson.get('generated_at') or '')
    compact = re.sub(r'\D', '', generated_at)
    if len(compact) >= 14:
        return compact[:14]
    return datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')


def _slugify(value: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', value.lower()).strip('-')
    return slug[:64] or str(uuid.uuid4())


class CliError(Exception):
    """A user-facing CLI failure."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


if __name__ == '__main__':
    raise SystemExit(main())
