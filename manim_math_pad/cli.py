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
from .engine.storyboard_generator import GeneratedStoryboard, StoryboardGenerator
from .engine.zettel_generator import ZettelGenerator


SCHEMA_VERSION = 1


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
    lesson = _load_json(args.lesson)
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
    lesson = _load_json(args.lesson)
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


def write_lesson_artifacts(
    lesson: dict[str, Any],
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Write a planned lesson artifact folder and return a manifest."""
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
        'lesson_id': lesson_id,
        'generated_at': generated_at,
        'concept': storyboard.concept,
        'domain': storyboard.domain,
        'summary': storyboard.summary,
        'target_duration_seconds': storyboard.target_duration_seconds,
        'lesson_plan': asdict(storyboard.lesson_plan),
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
        'lesson_id': lesson['lesson_id'],
        'concept': lesson['concept'],
        'domain': lesson['domain'],
        'summary': lesson['summary'],
        'target_duration_seconds': lesson['target_duration_seconds'],
        'lesson_plan': lesson['lesson_plan'],
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
    lines = [
        f'# {lesson["concept"].title()}',
        '',
        lesson['summary'],
        '',
        '## Learning Goal',
        '',
        plan['learning_goal'],
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
        lines.extend(
            [
                f'### {clip["index"]}. {clip["title"]}',
                '',
                f'- Duration: {clip["duration_seconds"]} seconds',
                f'- Purpose: {clip["purpose"]}',
                f'- Visual action: {clip["visual_action"]}',
                f'- Math focus: {clip["math_focus"]}',
                f'- Learner check: {clip["learner_check"]}',
                '',
                clip['narration'],
                '',
            ]
        )
    return '\n'.join(lines).rstrip() + '\n'


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


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise CliError(f'invalid JSON in {path}: {exc}', exit_code=2) from exc


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
