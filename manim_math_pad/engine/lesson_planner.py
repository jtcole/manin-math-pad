"""Lesson artifact planning for Manim Math Pad.

This module owns the shared lesson contract used by chat, storyboard rendering,
captions, CLI artifacts, and zettel notes. It keeps the editorial plan separate
from Manim execution so every downstream artifact is driven by the same teaching
decision.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .storyboard_generator import GeneratedStoryboard, StoryboardClip, StoryboardGenerator


SCHEMA_VERSION = 2
LESSON_SCHEMA_ID = 'https://codingenvironment.com/schemas/manim-math-pad/lesson.v2.json'

RESEARCH_BASIS = [
    {
        'principle': 'coherence',
        'implementation': 'Exclude nonessential on-screen text and decorative motion.',
        'source': 'Mayer, Cambridge Handbook of Multimedia Learning, chapter 12',
        'url': (
            'https://www.cambridge.org/core/books/abs/cambridge-handbook-of-multimedia-'
            'learning/principles-for-reducing-extraneous-processing-in-multimedia-learning-'
            'coherence-signaling-redundancy-spatial-contiguity-and-temporal-contiguity-'
            'principles/C98AB3A6CE760DD63C048936EA0B3B44'
        ),
    },
    {
        'principle': 'signaling',
        'implementation': 'Use motion, highlights, and local labels to point at the idea.',
        'source': 'Mayer, Cambridge Handbook of Multimedia Learning, chapter 12',
        'url': (
            'https://www.cambridge.org/core/books/abs/cambridge-handbook-of-multimedia-'
            'learning/principles-for-reducing-extraneous-processing-in-multimedia-learning-'
            'coherence-signaling-redundancy-spatial-contiguity-and-temporal-contiguity-'
            'principles/C98AB3A6CE760DD63C048936EA0B3B44'
        ),
    },
    {
        'principle': 'spatial_and_temporal_contiguity',
        'implementation': 'Place formulas beside the visual object while the action happens.',
        'source': 'Mayer, Cambridge Handbook of Multimedia Learning, chapter 12',
        'url': (
            'https://www.cambridge.org/core/books/abs/cambridge-handbook-of-multimedia-'
            'learning/principles-for-reducing-extraneous-processing-in-multimedia-learning-'
            'coherence-signaling-redundancy-spatial-contiguity-and-temporal-contiguity-'
            'principles/C98AB3A6CE760DD63C048936EA0B3B44'
        ),
    },
    {
        'principle': 'story_and_visual_intuition',
        'implementation': 'Make the learner want to resolve a visual question before naming symbols.',
        'source': 'Stanford Daily interview with Grant Sanderson',
        'url': (
            'https://stanforddaily.com/2020/01/24/3blue1brown-creator-grant-sanderson-15-'
            'talks-engaging-with-math-using-stories-and-visuals/'
        ),
    },
    {
        'principle': 'clip_pipeline',
        'implementation': 'Treat Manim as a clean clip renderer and assemble final media separately.',
        'source': '3Blue1Brown about Manim',
        'url': 'https://www.3blue1brown.com/about/',
    },
    {
        'principle': 'worked_example_and_retrieval',
        'implementation': 'Include one worked example and one checkable learner question.',
        'source': 'van den Broek, van Wermeskerken, and van Gog, Learning and Instruction',
        'url': (
            'https://research-portal.uu.nl/en/publications/retrieval-practice-in-stepwise-'
            'worked-examples-improves-learning/'
        ),
    },
]


@dataclass(frozen=True)
class PlannedLesson:
    """A generated lesson and the storyboard it came from."""

    storyboard: GeneratedStoryboard
    payload: dict[str, Any]
    markdown: str
    answer_markdown: str


class LessonPlanner:
    """Create a single reusable contract for all lesson artifacts."""

    def __init__(
        self,
        *,
        max_clips: int = 5,
        target_clip_seconds: int = 18,
    ):
        self.max_clips = max_clips
        self.target_clip_seconds = target_clip_seconds

    def plan(
        self,
        concept: str,
        *,
        context: dict | None = None,
        conversation: dict[str, Any] | list[Any] | None = None,
        lesson_id: str | None = None,
    ) -> PlannedLesson:
        """Plan a lesson from a concept and optional conversation context."""
        storyboard = StoryboardGenerator(
            max_clips=self.max_clips,
            target_clip_seconds=self.target_clip_seconds,
        ).generate(concept, context=context or {})
        resolved_lesson_id = lesson_id or lesson_id_from_concept(storyboard.concept)
        payload = lesson_payload(
            storyboard,
            resolved_lesson_id,
            conversation=conversation,
        )
        markdown = lesson_markdown(payload)
        answer = lesson_answer_markdown(payload)
        payload['lesson_markdown'] = markdown
        payload['answer_markdown'] = answer
        return PlannedLesson(
            storyboard=storyboard,
            payload=payload,
            markdown=markdown,
            answer_markdown=answer,
        )


def lesson_payload(
    storyboard: GeneratedStoryboard,
    lesson_id: str,
    *,
    conversation: dict[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    """Build the JSON lesson artifact from a generated storyboard."""
    generated_at = datetime.now(timezone.utc).isoformat()
    clips = [clip_payload(clip) for clip in storyboard.clips]
    subtitles = subtitle_payloads(clips)
    teaching_spec = teaching_spec_for_storyboard(storyboard)
    quality_gates = quality_gates_for_storyboard(storyboard)

    return {
        'schema_version': SCHEMA_VERSION,
        'schema_id': LESSON_SCHEMA_ID,
        'lesson_id': lesson_id,
        'generated_at': generated_at,
        'concept': storyboard.concept,
        'domain': storyboard.domain,
        'summary': storyboard.summary,
        'target_duration_seconds': storyboard.target_duration_seconds,
        'lesson_plan': asdict(storyboard.lesson_plan),
        'teaching_spec': teaching_spec,
        'research_basis': RESEARCH_BASIS,
        'quality_gates': quality_gates,
        'beats': [asdict(beat) for beat in storyboard.beats],
        'clips': clips,
        'subtitles': subtitles,
        'previous_concepts': storyboard.metadata.get('previous_concepts', []),
        'conversation': conversation,
        'metadata': {
            **storyboard.metadata,
            'lesson_id': lesson_id,
            'quality_gates': quality_gates,
        },
    }


def clip_payload(clip: StoryboardClip) -> dict[str, Any]:
    """Serialize a storyboard clip into the shared lesson contract."""
    return {
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


def subtitle_payloads(clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create WebVTT subtitle timing from lesson clips."""
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
    return subtitles


def teaching_spec_for_storyboard(storyboard: GeneratedStoryboard) -> dict[str, Any]:
    """Create the bot/MCP-facing teaching spec from a planned storyboard."""
    plan = storyboard.lesson_plan
    return {
        'diagnosis': {
            'learner_question': f'What does {storyboard.concept} mean visually?',
            'assumed_gap': assumed_gap(storyboard.domain),
            'misconception_to_surface': plan.misconception,
            'target_shift': (
                'Move the learner from symbol-recognition to a checkable visual model.'
            ),
        },
        'world_class_directive': {
            'one_sentence_standard': (
                'A viewer should be able to retell the visual story without seeing the '
                'source code or reading the hidden storyboard notes.'
            ),
            'visual_hierarchy': [
                'main mathematical object',
                'one local label or formula',
                'subtitles/captions for narration',
                'debug/source details hidden outside the frame',
            ],
            'failure_modes': [
                'large explanatory paragraphs in the video',
                'symbols appearing before the visual need is established',
                'clip transitions that reset the learner without context',
                'zettel notes that do not preserve the worked example or media source',
            ],
        },
        'visual_metaphor': visual_metaphor(storyboard.concept, storyboard.domain),
        'explainer_style': {
            'inspiration': '3Blue1Brown-style geometric explainer',
            'rules': [
                'Introduce one object at a time.',
                'Animate the mathematical action before naming the formula.',
                'Keep equations close to the object they describe.',
                'Use subtitles as narration, not as decorative labels.',
                'End each clip with one checkable question.',
            ],
            'research_principles': [item['principle'] for item in RESEARCH_BASIS],
        },
        'narrative_arc': [
            'Hook the learner with a visible question.',
            'Anchor the mathematical object.',
            'Animate the operation or limiting process.',
            'Expose the invariant or local relationship.',
            'Work one small example.',
            'Contrast the common misconception.',
            'Name the reusable takeaway.',
        ],
        'zettel_targets': zettel_targets(storyboard.concept, storyboard.domain),
        'clip_director_notes': [
            clip_director_note(storyboard.domain, storyboard.concept, clip)
            for clip in storyboard.clips
        ],
        'artifact_contract': {
            'lesson_markdown': 'lesson.md',
            'lesson_json': 'lesson.json',
            'storyboard_json': 'storyboard.json',
            'captions': 'captions.vtt',
            'clip_sources': 'clips/*.py',
            'rendered_clips': 'rendered_clips/*.mp4',
            'rendered_video': 'video.mp4',
            'thumbnail': 'thumbnail.jpg',
            'zettel_notes': 'zettel/*.md',
        },
    }


def quality_gates_for_storyboard(storyboard: GeneratedStoryboard) -> list[dict[str, str]]:
    """Checklist for judging whether the lesson is ready to publish."""
    return [
        {
            'name': 'visual_first',
            'check': 'Each clip uses motion or geometry as the primary explanation.',
            'evidence': 'Scene code avoids persistent goal/purpose/check panels.',
        },
        {
            'name': 'caption_not_wall_text',
            'check': 'Narration lives in captions and short local labels, not paragraphs.',
            'evidence': f'{len(storyboard.clips)} subtitle cues are generated from clip narration.',
        },
        {
            'name': 'worked_example',
            'check': 'The lesson includes one small computation or concrete example.',
            'evidence': storyboard.lesson_plan.example,
        },
        {
            'name': 'misconception_contrast',
            'check': 'The lesson explicitly contrasts the target idea with a likely wrong model.',
            'evidence': storyboard.lesson_plan.misconception,
        },
        {
            'name': 'knowledge_reuse',
            'check': 'The zettel cluster preserves the visual model, example, and media/code links.',
            'evidence': 'teaching_spec.zettel_targets and artifact_contract are populated.',
        },
    ]


def lesson_answer_markdown(lesson: dict[str, Any]) -> str:
    """User-facing lesson answer shown in chat."""
    plan = lesson['lesson_plan']
    teaching = lesson['teaching_spec']
    lines = [
        f'### {lesson["concept"].title()}',
        '',
        lesson['summary'],
        '',
        f'**Visual model:** {teaching["visual_metaphor"]}',
        '',
        f'**Learning goal:** {plan["learning_goal"]}',
        '',
        f'**Worked example:** {plan["example"]}',
        '',
        f'**Watch for:** {plan["misconception"]}',
        '',
        f'**Takeaway:** {plan["takeaway"]}',
    ]
    if lesson.get('previous_concepts'):
        lines.extend(
            [
                '',
                '**Session connection:** '
                + ', '.join(str(item) for item in lesson['previous_concepts'][-3:]),
            ]
        )
    return '\n'.join(lines).strip()


def lesson_markdown(lesson: dict[str, Any]) -> str:
    """Full lesson markdown for artifacts and vault notes."""
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
        '## Visual Story',
        '',
        teaching['visual_metaphor'],
        '',
        '## Teaching Diagnosis',
        '',
        f'- Learner question: {teaching["diagnosis"]["learner_question"]}',
        f'- Assumed gap: {teaching["diagnosis"]["assumed_gap"]}',
        f'- Target shift: {teaching["diagnosis"]["target_shift"]}',
        f'- Misconception: {teaching["diagnosis"]["misconception_to_surface"]}',
        '',
        '## Production Standard',
        '',
        teaching['world_class_directive']['one_sentence_standard'],
        '',
        '## Prerequisites',
        '',
        *[f'- {item}' for item in plan['prerequisites']],
        '',
        '## Worked Example',
        '',
        plan['example'],
        '',
        '## Misconception To Guard Against',
        '',
        plan['misconception'],
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

    lines.extend(
        [
            '## Quality Gates',
            '',
            *[
                f'- {gate["name"]}: {gate["check"]} Evidence: {gate["evidence"]}'
                for gate in lesson.get('quality_gates', [])
            ],
            '',
        ]
    )
    return '\n'.join(lines).rstrip() + '\n'


def public_lesson_payload(lesson: dict[str, Any], *, include_scene_code: bool = False) -> dict[str, Any]:
    """Return a browser/API-safe lesson payload."""
    clips = []
    for clip in lesson.get('clips', []):
        clip_copy = dict(clip)
        if not include_scene_code:
            clip_copy.pop('scene_code', None)
        clips.append(clip_copy)
    return {
        key: value
        for key, value in {
            'lesson_id': lesson.get('lesson_id'),
            'concept': lesson.get('concept'),
            'domain': lesson.get('domain'),
            'summary': lesson.get('summary'),
            'target_duration_seconds': lesson.get('target_duration_seconds'),
            'lesson_plan': lesson.get('lesson_plan'),
            'teaching_spec': lesson.get('teaching_spec'),
            'research_basis': lesson.get('research_basis'),
            'quality_gates': lesson.get('quality_gates'),
            'lesson_markdown': lesson.get('lesson_markdown'),
            'answer_markdown': lesson.get('answer_markdown'),
            'subtitles': lesson.get('subtitles'),
            'previous_concepts': lesson.get('previous_concepts'),
            'clips': clips,
        }.items()
        if value is not None
    }


def storyboard_payload_for_file(lesson: dict[str, Any]) -> dict[str, Any]:
    """Return storyboard.json content without embedding scene code."""
    public = public_lesson_payload(lesson, include_scene_code=False)
    public.update(
        {
            'schema_version': lesson['schema_version'],
            'schema_id': lesson['schema_id'],
            'beats': lesson['beats'],
        }
    )
    return public


def captions_vtt(lesson: dict[str, Any]) -> str:
    """Render a lesson's subtitles as WebVTT."""
    lines = ['WEBVTT', '']
    for subtitle in lesson['subtitles']:
        lines.extend(
            [
                str(subtitle['index']),
                (
                    f'{vtt_time(subtitle["start_seconds"])} --> '
                    f'{vtt_time(subtitle["end_seconds"])}'
                ),
                subtitle['text'],
                '',
            ]
        )
    return '\n'.join(lines)


def vtt_time(seconds: int | float) -> str:
    """Format seconds as WebVTT time."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{secs:02d}.000'


def assumed_gap(domain: str) -> str:
    gaps = {
        'calculus': 'The learner may know the formula but not the changing quantity.',
        'linear_algebra': 'The learner may see arrays of numbers but not transformations.',
        'complex_analysis': 'The learner may treat complex exponentials as symbolic tricks.',
        'general': 'The learner may not yet know the object, operation, and invariant.',
    }
    return gaps.get(domain, gaps['general'])


def visual_metaphor(concept: str, domain: str) -> str:
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


def zettel_targets(concept: str, domain: str) -> list[dict[str, str]]:
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
            'title': f'{topic} Media And Source',
            'type': 'artifact',
            'purpose': 'Link the lesson video, captions, and Manim code needed to recreate it.',
        },
        {
            'title': f'{topic} Connections',
            'type': 'connection',
            'purpose': f'Connect this {domain.replace("_", " ")} lesson to nearby concepts.',
        },
    ]


def clip_director_note(domain: str, concept: str, clip: StoryboardClip) -> dict[str, Any]:
    return {
        'clip_index': clip.index,
        'title': clip.title,
        'subtitle': clip.narration,
        'voiceover': clip.narration,
        'visual_primitives': visual_primitives(domain, concept, clip),
        'animation_actions': animation_actions(clip),
        'composition_notes': (
            'Use a stable corner progress marker, local labels attached to objects, '
            'and no persistent explanatory panels.'
        ),
        'asset_needs': asset_needs(domain, concept),
        'zettel_targets': [
            concept.title(),
            f'{concept.title()} Visual Model',
            f'{concept.title()} Worked Example',
            f'{concept.title()} Media And Source',
        ],
        'code_entrypoint': clip.scene_name,
    }


def visual_primitives(domain: str, concept: str, clip: StoryboardClip) -> list[str]:
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


def animation_actions(clip: StoryboardClip) -> list[str]:
    return [
        'fade in the object before text',
        clip.visual_action,
        'highlight the math focus with a local cue',
        'pause on the learner check in captions or the lesson notes',
    ]


def asset_needs(domain: str, concept: str) -> list[str]:
    lowered = concept.lower()
    if 'fourier' in lowered:
        return ['optional waveform audio/image reference for future richer renders']
    if domain == 'general':
        return ['optional domain-specific icon or sprite if the concept needs context']
    return []


def lesson_id_from_concept(concept: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    return f'{timestamp}_{slugify(concept)}'


def slugify(value: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', value.lower()).strip('-')
    return slug[:64] or str(uuid.uuid4())
