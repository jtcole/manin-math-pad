"""Generate multi-clip Manim storyboards from math concepts."""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field

from .chat_service import MathChatService
from .scene_generator import CONCEPT_DOMAINS, _scene_name_from_concept


@dataclass(frozen=True)
class StoryboardClip:
    """One renderable clip in a storyboard."""

    index: int
    title: str
    objective: str
    narration: str
    scene_name: str
    scene_code: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratedStoryboard:
    """A multi-step plan made of renderable Manim clips."""

    concept: str
    domain: str
    summary: str
    clips: list[StoryboardClip]
    metadata: dict = field(default_factory=dict)


class StoryboardGenerator:
    """Create connected animation clips for a concept.

    The queue still renders normal ``Animation`` rows. This generator supplies
    the clip-level scene code and metadata so one concept can render as several
    small, connected jobs instead of one oversized scene.
    """

    DEFAULT_BEATS = (
        'introduce the object',
        'show the operation or transformation',
        'track the invariant or accumulated quantity',
        'work through one concrete example',
        'state the final takeaway',
    )

    def __init__(self, max_clips: int = 5):
        self.max_clips = max(2, max_clips)

    def generate(self, concept: str, context: dict | None = None) -> GeneratedStoryboard:
        context = context or {}
        canonical = self._canonical_concept(concept)
        domain = self._match_domain(canonical)
        beats = self._beats_for(canonical)[: self.max_clips]
        previous = self._previous_concepts(context, canonical)
        summary = self._summary(canonical, domain, beats, previous)

        clips = [
            self._build_clip(
                concept=canonical,
                domain=domain,
                beat=beat,
                index=index,
                clip_count=len(beats),
                previous=previous,
            )
            for index, beat in enumerate(beats, start=1)
        ]
        return GeneratedStoryboard(
            concept=canonical,
            domain=domain,
            summary=summary,
            clips=clips,
            metadata={
                'source': 'storyboard',
                'clip_count': len(clips),
                'previous_concepts': previous,
                'beats': list(beats),
            },
        )

    def _canonical_concept(self, concept: str) -> str:
        return MathChatService(enable_llm_chat=False)._focus_concept(concept)

    def _match_domain(self, concept: str) -> str:
        lowered = concept.lower()
        for domain, keywords in CONCEPT_DOMAINS.items():
            if any(keyword in lowered for keyword in keywords):
                return domain
        return 'general'

    def _beats_for(self, concept: str) -> tuple[str, ...]:
        profile = MathChatService(enable_llm_chat=False)._known_profile(concept)
        if profile:
            return profile.animation_steps
        return self.DEFAULT_BEATS

    def _previous_concepts(self, context: dict, concept: str) -> list[str]:
        values = context.get('previous_concepts') or context.get('concepts') or []
        return [
            str(item).strip()
            for item in values
            if str(item).strip() and str(item).strip() != concept
        ][-3:]

    def _summary(
        self,
        concept: str,
        domain: str,
        beats: tuple[str, ...],
        previous: list[str],
    ) -> str:
        connection = ''
        if previous:
            connection = f' It connects back to {", ".join(previous)}.'
        return (
            f'{concept.title()} is split into {len(beats)} clips so each render can '
            f'focus on one visible mathematical move in {domain.replace("_", " ")}.'
            f'{connection}'
        )

    def _build_clip(
        self,
        concept: str,
        domain: str,
        beat: str,
        index: int,
        clip_count: int,
        previous: list[str],
    ) -> StoryboardClip:
        title = self._clip_title(beat)
        narration = self._narration(concept, domain, beat, index, previous)
        scene_name = _scene_name_from_concept(f'{concept} storyboard clip {index}')
        scene_code = self._clip_scene_code(
            scene_name=scene_name,
            concept=concept,
            domain=domain,
            title=title,
            narration=narration,
            beat=beat,
            index=index,
            clip_count=clip_count,
        )
        return StoryboardClip(
            index=index,
            title=title,
            objective=beat,
            narration=narration,
            scene_name=scene_name,
            scene_code=scene_code,
            metadata={
                'domain': domain,
                'beat': beat,
                'clip_index': index,
                'clip_count': clip_count,
                'previous_concepts': previous,
            },
        )

    def _clip_title(self, beat: str) -> str:
        clean = re.sub(r'\s+', ' ', beat.strip())
        return clean[:1].upper() + clean[1:]

    def _narration(
        self,
        concept: str,
        domain: str,
        beat: str,
        index: int,
        previous: list[str],
    ) -> str:
        role = [
            'set up the visual object',
            'make the mathematical action explicit',
            'slow down the key comparison',
            'work through a concrete check',
            'name the takeaway',
        ][min(index - 1, 4)]
        prior = ''
        if previous:
            prior = f' Compare the move with {", ".join(previous)}.'
        return (
            f'This {domain.replace("_", " ")} clip should {role}: {beat}. '
            f'Keep the viewer focused on what changes and what remains meaningful '
            f'for {concept}.{prior}'
        )

    def _clip_scene_code(
        self,
        scene_name: str,
        concept: str,
        domain: str,
        title: str,
        narration: str,
        beat: str,
        index: int,
        clip_count: int,
    ) -> str:
        lines = textwrap.wrap(narration, width=64)[:4]
        visual_code = self._visual_code(domain, concept)
        return f'''
from manim import *


class {scene_name}(Scene):
    """Storyboard clip for {concept}."""

    def construct(self):
        concept = {concept!r}
        domain = {domain!r}
        clip_title = {title!r}
        beat = {beat!r}
        narration_lines = {lines!r}

        def fitted_text(value, font_size=30, width=11.2, color=WHITE):
            text = Text(value, font_size=font_size, color=color)
            if text.width > width:
                text.scale_to_fit_width(width)
            return text

        header = VGroup(
            fitted_text(concept.title(), font_size=34, width=10.2),
            fitted_text(f"Clip {index} of {clip_count}: {{clip_title}}", font_size=24, width=10.8, color=YELLOW),
        ).arrange(DOWN, buff=0.16)
        header.to_edge(UP)

        progress = VGroup(*[
            Rectangle(
                width=0.72,
                height=0.09,
                stroke_width=0,
                fill_color=YELLOW if step <= {index} else GREY,
                fill_opacity=1 if step <= {index} else 0.32,
            )
            for step in range(1, {clip_count + 1})
        ]).arrange(RIGHT, buff=0.08)
        progress.next_to(header, DOWN, buff=0.22)

{visual_code}
        visual.move_to(ORIGIN).shift(DOWN * 0.1)

        objective = fitted_text(beat, font_size=28, width=11, color=BLUE)
        objective.next_to(visual, UP, buff=0.34)

        narration = VGroup(*[
            fitted_text(line, font_size=22, width=11.2, color=GREY_B)
            for line in narration_lines
        ]).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        narration.to_edge(DOWN)

        self.play(Write(header), FadeIn(progress), run_time=1.2)
        self.play(Create(visual), run_time=2.4)
        self.play(Write(objective), run_time=1.1)
        self.play(FadeIn(narration), run_time=1.1)
        self.wait(2.2)
'''.strip()

    def _visual_code(self, domain: str, concept: str) -> str:
        lowered = concept.lower()
        if domain == 'calculus':
            return '''        axes = Axes(
            x_range=[-1, 3, 1],
            y_range=[-0.5, 4, 1],
            x_length=5.2,
            y_length=3.1,
            tips=False,
        )
        curve = axes.plot(
            lambda x: 0.45 * (x - 0.35) ** 2 + 0.35,
            x_range=[-0.7, 2.8],
            color=BLUE,
        )
        base = Dot(axes.c2p(0.8, 0.45 * (0.8 - 0.35) ** 2 + 0.35), color=YELLOW)
        moving = Dot(axes.c2p(2.1, 0.45 * (2.1 - 0.35) ** 2 + 0.35), color=GREEN)
        secant = Line(base.get_center(), moving.get_center(), color=GREEN)
        tangent = Line(
            axes.c2p(0.05, 0.15),
            axes.c2p(1.65, 1.65),
            color=YELLOW,
        )
        visual = VGroup(axes, curve, secant, tangent, base, moving).scale(0.9)
'''
        if domain == 'linear_algebra':
            return '''        matrix_a = Matrix([["1", "2"], ["3", "4"]]).scale(0.55).set_color(BLUE)
        times = MathTex(r"\\\\times", font_size=38)
        matrix_b = Matrix([["5", "6"], ["7", "8"]]).scale(0.55).set_color(GREEN)
        equals = MathTex("=", font_size=38)
        result = Matrix([["19", "22"], ["43", "50"]]).scale(0.55).set_color(YELLOW)
        visual = VGroup(matrix_a, times, matrix_b, equals, result).arrange(RIGHT, buff=0.25)
'''
        if domain == 'complex_analysis' or 'euler' in lowered or 'fourier' in lowered:
            return '''        circle = Circle(radius=1.25, color=BLUE)
        real_axis = Line(LEFT * 1.6, RIGHT * 1.6, color=GREY)
        imag_axis = Line(DOWN * 1.6, UP * 1.6, color=GREY)
        point = Dot(circle.point_at_angle(PI), color=YELLOW)
        radius = Arrow(ORIGIN, point.get_center(), buff=0, color=YELLOW)
        label = MathTex(r"e^{it}", font_size=36).next_to(circle, RIGHT, buff=0.45)
        visual = VGroup(circle, real_axis, imag_axis, radius, point, label)
'''
        return '''        source = Circle(radius=0.7, color=BLUE)
        operation = Arrow(LEFT * 1.0, RIGHT * 1.0, color=YELLOW)
        target = Square(side_length=1.2, color=GREEN).next_to(operation, RIGHT, buff=0.45)
        source.next_to(operation, LEFT, buff=0.45)
        invariant = Text("invariant", font_size=24, color=YELLOW).next_to(operation, UP)
        visual = VGroup(source, operation, target, invariant)
'''
