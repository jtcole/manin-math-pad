"""Generate pedagogical multi-clip Manim storyboards from math concepts."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .chat_service import MathChatService
from .scene_generator import CONCEPT_DOMAINS, _scene_name_from_concept


@dataclass(frozen=True)
class LessonPlan:
    """The teaching intent behind a storyboard."""

    concept: str
    audience_level: str
    learning_goal: str
    prerequisites: tuple[str, ...]
    misconception: str
    example: str
    takeaway: str


@dataclass(frozen=True)
class StoryboardBeat:
    """One planned teaching move in a storyboard."""

    index: int
    title: str
    duration_seconds: int
    purpose: str
    visual_action: str
    math_focus: str
    narration: str
    learner_check: str


@dataclass(frozen=True)
class StoryboardClip:
    """One renderable clip in a storyboard."""

    index: int
    title: str
    objective: str
    narration: str
    scene_name: str
    scene_code: str
    duration_seconds: int
    purpose: str
    visual_action: str
    math_focus: str
    learner_check: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratedStoryboard:
    """A multi-step lesson plan made of renderable Manim clips."""

    concept: str
    domain: str
    summary: str
    lesson_plan: LessonPlan
    beats: list[StoryboardBeat]
    clips: list[StoryboardClip]
    target_duration_seconds: int
    metadata: dict = field(default_factory=dict)


class StoryboardGenerator:
    """Plan and compile connected animation clips for a concept.

    This class deliberately separates lesson planning from Manim code emission.
    The resulting clips remain normal render jobs, but each one now carries a
    teaching purpose, target duration, visual action, math focus, and learner
    check.
    """

    DEFAULT_LESSON = LessonPlan(
        concept='math concept',
        audience_level='curious learner',
        learning_goal='Understand the objects, operation, invariant, and takeaway.',
        prerequisites=('basic notation', 'one concrete example'),
        misconception='Do not treat the notation as meaningful before the objects are named.',
        example='Use the smallest example that can be computed by hand.',
        takeaway='A useful mathematical idea names what changes and what remains stable.',
    )

    DEFAULT_BEATS = (
        StoryboardBeat(
            index=1,
            title='Set Up The Object',
            duration_seconds=18,
            purpose='Anchor the concept in a visible object.',
            visual_action='Show the starting object and label the pieces that matter.',
            math_focus='object, representation, and labels',
            narration='Start by naming the object and the representation we will track.',
            learner_check='Can you point to the object and name the data attached to it?',
        ),
        StoryboardBeat(
            index=2,
            title='Show The Operation',
            duration_seconds=18,
            purpose='Make the mathematical action visible.',
            visual_action='Apply the operation and show what moves or changes.',
            math_focus='operation and output',
            narration='Now apply the operation slowly enough that the change is visible.',
            learner_check='What changed, and what stayed meaningful?',
        ),
        StoryboardBeat(
            index=3,
            title='Track The Invariant',
            duration_seconds=18,
            purpose='Identify the quantity or structure that remains meaningful.',
            visual_action='Highlight the stable relationship while the representation changes.',
            math_focus='invariant or accumulated quantity',
            narration='The invariant is the reason the concept is reusable.',
            learner_check='Which part can be checked again in a different example?',
        ),
        StoryboardBeat(
            index=4,
            title='Work A Small Example',
            duration_seconds=18,
            purpose='Make the abstraction hand-checkable.',
            visual_action='Run one small numeric example from start to finish.',
            math_focus='concrete computation',
            narration='A small computation keeps the idea from becoming only a slogan.',
            learner_check='Can you reproduce the example without the animation?',
        ),
        StoryboardBeat(
            index=5,
            title='State The Takeaway',
            duration_seconds=15,
            purpose='Separate the durable lesson from the visual setup.',
            visual_action='Summarize the object, operation, invariant, and conclusion together.',
            math_focus='final takeaway',
            narration='End by naming the reusable move the learner should remember.',
            learner_check='What would you look for in the next problem?',
        ),
    )

    def __init__(self, max_clips: int = 5, target_clip_seconds: int = 18):
        self.max_clips = max(2, max_clips)
        self.target_clip_seconds = max(12, target_clip_seconds)

    def generate(self, concept: str, context: dict | None = None) -> GeneratedStoryboard:
        context = context or {}
        canonical = self._canonical_concept(concept)
        domain = self._match_domain(canonical)
        lesson = self._lesson_for(canonical, domain)
        previous = self._previous_concepts(context, canonical)
        beats = self._planned_beats(canonical, lesson)
        beats = self._limit_beats(beats)
        beats = self._retime_beats(beats)
        summary = self._summary(lesson, domain, beats, previous)

        clips = [
            self._build_clip(
                concept=canonical,
                domain=domain,
                lesson=lesson,
                beat=beat,
                clip_count=len(beats),
                previous=previous,
            )
            for beat in beats
        ]
        target_duration = sum(clip.duration_seconds for clip in clips)
        return GeneratedStoryboard(
            concept=canonical,
            domain=domain,
            summary=summary,
            lesson_plan=lesson,
            beats=beats,
            clips=clips,
            target_duration_seconds=target_duration,
            metadata={
                'source': 'pedagogical_storyboard',
                'clip_count': len(clips),
                'target_duration_seconds': target_duration,
                'target_clip_seconds': self.target_clip_seconds,
                'previous_concepts': previous,
                'lesson_plan': asdict(lesson),
                'storyboard_plan': [asdict(beat) for beat in beats],
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

    def _lesson_for(self, concept: str, domain: str) -> LessonPlan:
        lowered = concept.lower()
        if 'gamma' in lowered:
            return LessonPlan(
                concept=concept,
                audience_level='curious calculus learner',
                learning_goal=(
                    'Understand the gamma function as the visual answer to the question: '
                    'what should factorial mean between the whole numbers?'
                ),
                prerequisites=(
                    'factorials',
                    'area under a curve',
                    'exponential decay',
                    'function recurrence',
                ),
                misconception=(
                    'The gamma function is not just a pretty curve through factorial dots; '
                    'matching the dots is easy, but the recurrence and shape constraints do '
                    'the real mathematical work.'
                ),
                example=(
                    'Gamma(5)=4!=24, while Gamma(1/2)=sqrt(pi), so Euler\'s integral turns '
                    'between-integer factorials into measurable areas.'
                ),
                takeaway=(
                    'Gamma turns factorial from a discrete recipe into a continuous machine '
                    'governed by the one-step rule Gamma(x+1)=x Gamma(x).'
                ),
            )
        if 'derivative' in lowered:
            return LessonPlan(
                concept=concept,
                audience_level='early calculus',
                learning_goal='Understand a derivative as the limit of average slopes.',
                prerequisites=('function graph', 'slope', 'limit', 'secant line'),
                misconception='The derivative is not the height of the graph; it is local slope.',
                example='For f(x)=x^2 at x=3, the slope approaches 6 as h approaches 0.',
                takeaway='A derivative is the number a secant slope approaches when the second point collapses onto the first.',
            )
        if 'limit' in lowered:
            return LessonPlan(
                concept=concept,
                audience_level='early calculus',
                learning_goal='Understand a limit as forced nearby behavior.',
                prerequisites=('function values', 'approaching from both sides', 'output tolerance'),
                misconception='A limit does not require the function to be defined at the target point.',
                example='(x^2 - 1)/(x - 1) behaves like x + 1 near x=1, so the limit is 2.',
                takeaway='A limit records what nearby values force the output to approach.',
            )
        if 'matrix' in lowered:
            return LessonPlan(
                concept=concept,
                audience_level='linear algebra learner',
                learning_goal='Understand matrix multiplication as row-column composition.',
                prerequisites=('vectors', 'dot product', 'matrix dimensions'),
                misconception='Matrix multiplication is not entry-by-entry multiplication.',
                example='The top-left entry of [[1,2],[3,4]][[5,6],[7,8]] is 1*5 + 2*7 = 19.',
                takeaway='Each product entry is one row asking a column for a weighted total.',
            )
        if 'euler' in lowered:
            return LessonPlan(
                concept=concept,
                audience_level='precalculus or complex numbers learner',
                learning_goal='Understand Euler identity as rotation in complex coordinates.',
                prerequisites=('unit circle', 'angle in radians', 'complex plane', 'cosine and sine'),
                misconception='Euler identity is not numerology; it is a coordinate statement about rotation.',
                example='At t=pi, cos(pi)=-1 and sin(pi)=0, so e^(i*pi)=-1.',
                takeaway='The identity e^(i*pi)+1=0 says a half-turn lands exactly on -1.',
            )
        if 'fourier' in lowered:
            return LessonPlan(
                concept=concept,
                audience_level='signals or calculus learner',
                learning_goal='Understand a Fourier series as simple waves building a periodic shape.',
                prerequisites=('sine waves', 'periodic functions', 'amplitude', 'frequency'),
                misconception='A Fourier series is not arbitrary curve fitting; each frequency is a component.',
                example='A square wave becomes sharper as odd sine harmonics are added.',
                takeaway='Fourier series explain complicated repetition by adding simple independent frequencies.',
            )
        lesson = self.DEFAULT_LESSON
        return LessonPlan(
            concept=concept,
            audience_level=lesson.audience_level,
            learning_goal=lesson.learning_goal,
            prerequisites=lesson.prerequisites,
            misconception=lesson.misconception,
            example=lesson.example,
            takeaway=lesson.takeaway,
        )

    def _planned_beats(self, concept: str, lesson: LessonPlan) -> list[StoryboardBeat]:
        lowered = concept.lower()
        if 'gamma' in lowered:
            return [
                StoryboardBeat(
                    1,
                    'Start With Factorial Islands',
                    22,
                    'Turn the historical problem into a visible gap between integer dots.',
                    'Plot 0!, 1!, 2!, 3!, and 4! as isolated dots, then ask what the curve should do between them.',
                    'factorial values are known only at whole numbers',
                    'Euler starts with a simple itch: factorials leap from dot to dot, but analysis wants values between the dots.',
                    'Which values are known before any curve is drawn?',
                ),
                StoryboardBeat(
                    2,
                    'Demand The Step Rule',
                    22,
                    'Show why any candidate must preserve the factorial recurrence.',
                    'Draw the gamma curve through the dots and add ladder arrows for Gamma(x+1)=x Gamma(x).',
                    'Gamma(x+1)=x Gamma(x)',
                    'A useful extension has to remember the factorial engine: move one step right, multiply by the current input.',
                    'What rule survives after we leave the integers?',
                ),
                StoryboardBeat(
                    3,
                    'Reveal Euler\'s Area Machine',
                    24,
                    'Replace curve guessing with a concrete integral that produces the values.',
                    'Morph to an area under t^(x-1)e^(-t) and keep the integral beside the shaded region.',
                    'Gamma(x)=integral_0^infinity t^(x-1)e^(-t) dt',
                    'Euler\'s move is not to draw a convenient curve by hand; it is to build an area machine whose output changes smoothly with x.',
                    'What object is being measured when x is not an integer?',
                ),
                StoryboardBeat(
                    4,
                    'Check The Integer Stops',
                    22,
                    'Prove the new machine still agrees with factorial where factorial already exists.',
                    'Show Gamma(1), Gamma(2), Gamma(3), and Gamma(5) as checkpoints on the same curve.',
                    'Gamma(n+1)=n!',
                    'At the integer stops, the area machine snaps back to the familiar factorial numbers.',
                    'Which gamma input corresponds to 4!?',
                ),
                StoryboardBeat(
                    5,
                    'Name The New Terrain',
                    20,
                    'Contrast useful extension with arbitrary interpolation and point to what gamma unlocks.',
                    'Show a second curve through the same dots, reject it, then keep the recurrence, area, and shape constraints highlighted.',
                    'matching dots is not uniqueness',
                    'The new problem is subtle: many curves can touch the same dots, so gamma becomes important because its rules travel into probability, asymptotics, and the complex plane.',
                    'Why is matching all the factorial dots not enough?',
                ),
            ]
        if 'derivative' in lowered:
            return [
                StoryboardBeat(
                    1,
                    'Anchor Average Slope',
                    18,
                    'Show why a derivative starts from an average rate of change.',
                    'Draw a curve, choose two nearby points, and connect them with a secant line.',
                    'average slope = rise / run',
                    'The derivative question starts with something familiar: the slope between two visible points.',
                    'Where are the two points, and what does the secant slope measure?',
                ),
                StoryboardBeat(
                    2,
                    'Shrink The Gap',
                    20,
                    'Turn the average slope into a limiting process.',
                    'Move the second point toward the base point while the secant line updates.',
                    'slope(h) = (f(x+h) - f(x)) / h',
                    'As h gets smaller, the average slope is forced to describe more local behavior.',
                    'What quantity changes as h shrinks, and what is trying to settle down?',
                ),
                StoryboardBeat(
                    3,
                    'Name The Tangent Limit',
                    18,
                    'Connect the moving secant to the tangent slope.',
                    'Freeze the limiting line and label it as the tangent direction.',
                    "f'(x) = lim h->0 (f(x+h)-f(x))/h",
                    'The tangent line is not guessed; it is the line the secants approach.',
                    'Why is the tangent slope a limit instead of a separate rule?',
                ),
                StoryboardBeat(
                    4,
                    'Check A Polynomial',
                    20,
                    'Compute one example so the visual claim becomes testable.',
                    'Substitute f(x)=x^2 and simplify the difference quotient at x=3.',
                    '(3+h)^2 - 9 over h = 6 + h -> 6',
                    'For x squared, the algebra agrees with the picture: the local slope at x=3 is 6.',
                    'Which term disappears only because h approaches zero?',
                ),
                StoryboardBeat(
                    5,
                    'Guard The Misconception',
                    16,
                    'Separate graph height from graph slope.',
                    'Contrast the point height with the tangent slope and keep only the slope highlighted.',
                    'derivative = local rate of change, not y-value',
                    'The final takeaway is that a derivative measures local change, not where the graph sits.',
                    'If two graphs pass through the same point, must their derivatives match?',
                ),
            ]
        if 'matrix' in lowered:
            return [
                StoryboardBeat(
                    1,
                    'Set Dimensions',
                    17,
                    'Show which dimensions must line up before multiplication is allowed.',
                    'Place A, B, and the output matrix side by side.',
                    'A is 2x2, B is 2x2, AB is 2x2',
                    'Before computing, check the shapes: the inner dimensions tell us rows can meet columns.',
                    'Which dimension is summed away?',
                ),
                StoryboardBeat(
                    2,
                    'Highlight Row And Column',
                    18,
                    'Make one product entry visible as a row-column pairing.',
                    'Highlight row 1 of A and column 1 of B.',
                    'c11 uses row 1 and column 1',
                    'Each entry in the result comes from one row asking one column for a dot product.',
                    'Which row and column produce the top-left entry?',
                ),
                StoryboardBeat(
                    3,
                    'Compute One Entry',
                    20,
                    'Compute the top-left entry slowly.',
                    'Multiply paired entries and sum the products.',
                    'c11 = 1*5 + 2*7 = 19',
                    'The dot product is the whole rule in miniature: pair, multiply, then add.',
                    'Where did the 19 come from?',
                ),
                StoryboardBeat(
                    4,
                    'Repeat The Rule',
                    18,
                    'Show that the same row-column rule fills every entry.',
                    'Move the highlight to the other entries and reveal the finished matrix.',
                    'C = [[19,22],[43,50]]',
                    'Nothing new happens for the other entries; the same operation repeats with different row-column pairs.',
                    'Why is this not entry-by-entry multiplication?',
                ),
            ]
        if 'euler' in lowered:
            return [
                StoryboardBeat(
                    1,
                    'Place The Complex Plane',
                    17,
                    'Set up the unit circle as the stage for complex exponentials.',
                    'Draw real and imaginary axes, the unit circle, and the point at 1.',
                    'e^(it) lives on the unit circle',
                    'Euler formula is easiest to see as motion around the unit circle.',
                    'Where is the point when t=0?',
                ),
                StoryboardBeat(
                    2,
                    'Rotate Through Pi',
                    20,
                    'Show the exponential as rotation.',
                    'Move the point through a half-turn from angle 0 to pi.',
                    'e^(it) = cos(t) + i sin(t)',
                    'As t changes, cosine and sine are the coordinates of the rotating point.',
                    'Which coordinate changes from 1 to -1?',
                ),
                StoryboardBeat(
                    3,
                    'Read The Coordinates',
                    18,
                    'Substitute t=pi in the coordinate form.',
                    'Freeze the point at -1 and show cosine and sine values.',
                    'cos(pi)=-1 and sin(pi)=0',
                    'At pi radians, the vertical coordinate is zero and the horizontal coordinate is -1.',
                    'Why does the imaginary part disappear?',
                ),
                StoryboardBeat(
                    4,
                    'State The Identity',
                    16,
                    'Connect the rotation result to the famous equation.',
                    'Transform e^(i*pi)=-1 into e^(i*pi)+1=0.',
                    'e^(i*pi) + 1 = 0',
                    'The identity compresses rotation, coordinates, and arithmetic into one statement.',
                    'What part of the equation represents the half-turn?',
                ),
            ]
        if 'fourier' in lowered:
            return [
                StoryboardBeat(
                    1,
                    'Show The Target Signal',
                    17,
                    'Make the periodic target visible before decomposing it.',
                    'Draw a repeating square-like signal and label its period.',
                    'target = periodic shape',
                    'Fourier analysis starts with a repeating shape we want to understand.',
                    'What feature repeats?',
                ),
                StoryboardBeat(
                    2,
                    'Add The First Wave',
                    18,
                    'Show the first sine wave as the roughest approximation.',
                    'Draw the first sine component over the target.',
                    'first harmonic',
                    'The first wave captures the broad motion but not the sharp corners.',
                    'What part of the target is still missing?',
                ),
                StoryboardBeat(
                    3,
                    'Add Harmonics',
                    20,
                    'Show higher frequencies improving the approximation.',
                    'Add third and fifth harmonics with smaller amplitudes.',
                    'sin(x) + sin(3x)/3 + sin(5x)/5',
                    'Higher frequencies sharpen details while contributing smaller corrections.',
                    'Why do sharper edges need higher frequencies?',
                ),
                StoryboardBeat(
                    4,
                    'State The Decomposition',
                    16,
                    'Connect the visual sum to the reusable idea.',
                    'Group the component waves and the approximation as one decomposition.',
                    'signal = sum of frequency components',
                    'The takeaway is not just fitting a curve; it is separating a signal into independent rhythms.',
                    'What would each coefficient measure?',
                ),
            ]
        return list(self.DEFAULT_BEATS)

    def _limit_beats(self, beats: list[StoryboardBeat]) -> list[StoryboardBeat]:
        if len(beats) <= self.max_clips:
            limited = beats
        else:
            limited = [*beats[: self.max_clips - 1], beats[-1]]
        return [
            StoryboardBeat(
                index=index,
                title=beat.title,
                duration_seconds=beat.duration_seconds,
                purpose=beat.purpose,
                visual_action=beat.visual_action,
                math_focus=beat.math_focus,
                narration=beat.narration,
                learner_check=beat.learner_check,
            )
            for index, beat in enumerate(limited, start=1)
        ]

    def _retime_beats(self, beats: list[StoryboardBeat]) -> list[StoryboardBeat]:
        retimed = []
        for beat in beats:
            retimed.append(
                StoryboardBeat(
                    index=beat.index,
                    title=beat.title,
                    duration_seconds=max(beat.duration_seconds, self.target_clip_seconds),
                    purpose=beat.purpose,
                    visual_action=beat.visual_action,
                    math_focus=beat.math_focus,
                    narration=beat.narration,
                    learner_check=beat.learner_check,
                )
            )
        return retimed

    def _previous_concepts(self, context: dict, concept: str) -> list[str]:
        values = context.get('previous_concepts') or context.get('concepts') or []
        return [
            str(item).strip()
            for item in values
            if str(item).strip() and str(item).strip() != concept
        ][-3:]

    def _summary(
        self,
        lesson: LessonPlan,
        domain: str,
        beats: list[StoryboardBeat],
        previous: list[str],
    ) -> str:
        connection = ''
        if previous:
            connection = f' It connects back to {", ".join(previous)}.'
        duration = sum(beat.duration_seconds for beat in beats)
        return (
            f'{lesson.concept.title()} is planned as a {duration}-second '
            f'{domain.replace("_", " ")} lesson over {len(beats)} clips. '
            f'Goal: {lesson.learning_goal} Misconception to guard against: '
            f'{lesson.misconception}{connection}'
        )

    def _build_clip(
        self,
        concept: str,
        domain: str,
        lesson: LessonPlan,
        beat: StoryboardBeat,
        clip_count: int,
        previous: list[str],
    ) -> StoryboardClip:
        scene_name = _scene_name_from_concept(f'{concept} storyboard clip {beat.index}')
        scene_code = self._clip_scene_code(
            scene_name=scene_name,
            concept=concept,
            domain=domain,
            lesson=lesson,
            beat=beat,
            clip_count=clip_count,
        )
        return StoryboardClip(
            index=beat.index,
            title=beat.title,
            objective=beat.purpose,
            narration=beat.narration,
            scene_name=scene_name,
            scene_code=scene_code,
            duration_seconds=beat.duration_seconds,
            purpose=beat.purpose,
            visual_action=beat.visual_action,
            math_focus=beat.math_focus,
            learner_check=beat.learner_check,
            metadata={
                'domain': domain,
                'beat': asdict(beat),
                'lesson_plan': asdict(lesson),
                'clip_index': beat.index,
                'clip_count': clip_count,
                'target_duration_seconds': beat.duration_seconds,
                'previous_concepts': previous,
            },
        )

    def _clip_scene_code(
        self,
        scene_name: str,
        concept: str,
        domain: str,
        lesson: LessonPlan,
        beat: StoryboardBeat,
        clip_count: int,
    ) -> str:
        visual_code = self._visual_code(domain, concept, beat)
        action_code = self._visual_action_code(domain, concept, beat)
        return f'''
from manim import *
import math


class {scene_name}(Scene):
    """Pedagogical storyboard clip for {concept}."""

    def construct(self):
        concept = {concept!r}
        duration_seconds = {beat.duration_seconds!r}

        def fitted_text(value, font_size=18, width=3.6, color=GREY_B):
            text = Text(value, font_size=font_size, color=color)
            if text.width > width:
                text.scale_to_fit_width(width)
            return text

        scene_tag = fitted_text(f"{{concept.title()}}  {beat.index}/{clip_count}", width=3.2)
        scene_tag.to_corner(UL, buff=0.28)
        scene_tag.set_opacity(0.62)

        progress = VGroup(*[
            Rectangle(
                width=0.32,
                height=0.045,
                stroke_width=0,
                fill_color=YELLOW if step <= {beat.index} else GREY,
                fill_opacity=0.76 if step <= {beat.index} else 0.2,
            )
            for step in range(1, {clip_count + 1})
        ]).arrange(RIGHT, buff=0.08)
        progress.to_corner(UR, buff=0.32)

{visual_code}

        self.play(FadeIn(scene_tag), FadeIn(progress), run_time=0.5)
{action_code}
        self.wait(max(duration_seconds - 10.0, 3.0))
'''.strip()

    def _visual_code(self, domain: str, concept: str, beat: StoryboardBeat) -> str:
        lowered = concept.lower()
        if 'gamma' in lowered:
            return '''        factorial_axes = Axes(
            x_range=[-0.2, 4.4, 1],
            y_range=[0, 26, 5],
            x_length=7.4,
            y_length=4.15,
            tips=False,
        )
        factorial_axes.shift(LEFT * 0.75 + DOWN * 0.1)
        axis_labels = VGroup(
            Text("input", font_size=18, color=GREY_B).next_to(factorial_axes.x_axis, RIGHT, buff=0.12),
            Text("factorial value", font_size=18, color=GREY_B)
            .next_to(factorial_axes.y_axis, UP, buff=0.12),
        )
        factorial_dots = VGroup(
            *[
                Dot(
                    factorial_axes.c2p(n, math.factorial(n)),
                    radius=0.07,
                    color=YELLOW,
                )
                for n in range(5)
            ]
        )
        factorial_labels = VGroup(
            *[
                MathTex(label, font_size=24, color=YELLOW).next_to(
                    factorial_dots[index],
                    UR,
                    buff=0.08,
                )
                for index, label in enumerate([r"0!=1", r"1!=1", r"2!=2", r"3!=6", r"4!=24"])
            ]
        )
        gamma_curve = factorial_axes.plot(
            lambda x: math.gamma(x + 1),
            x_range=[0, 4.0],
            color=BLUE,
        )
        alternative_curve = factorial_axes.plot(
            lambda x: math.gamma(x + 1) * (1 + 0.09 * math.sin(2 * PI * x)),
            x_range=[0, 4.0],
            color=RED,
        )
        alternative_curve.set_stroke(opacity=0.55)
        question = Text(
            "Fill in the factorial gaps",
            font_size=28,
            color=YELLOW,
        ).to_edge(DOWN, buff=0.42)
        recurrence = MathTex(r"\\Gamma(x+1)=x\\Gamma(x)", font_size=38, color=YELLOW)
        recurrence.to_edge(DOWN, buff=0.42)
        ladder_arrows = VGroup(
            *[
                Arrow(
                    factorial_axes.c2p(x, math.gamma(x + 1)),
                    factorial_axes.c2p(x + 1, math.gamma(x + 2)),
                    buff=0.05,
                    color=YELLOW,
                    stroke_width=4,
                    max_tip_length_to_length_ratio=0.12,
                )
                for x in [0.45, 1.15, 1.85]
            ]
        )
        integral_axes = Axes(
            x_range=[0, 8, 2],
            y_range=[0, 0.62, 0.2],
            x_length=6.7,
            y_length=3.45,
            tips=False,
        )
        integral_axes.shift(DOWN * 0.05)
        integrand = integral_axes.plot(
            lambda t: (t ** 2) * math.exp(-t),
            x_range=[0, 8],
            color=BLUE,
        )
        area = integral_axes.get_area(
            integrand,
            x_range=[0, 8],
            color=BLUE,
            opacity=0.32,
        )
        integral_formula = MathTex(
            r"\\Gamma(x)=\\int_0^\\infty t^{x-1}e^{-t}\\,dt",
            font_size=35,
            color=YELLOW,
        )
        integral_formula.next_to(integral_axes, DOWN, buff=0.34)
        area_label = Text("area changes as x changes", font_size=24, color=YELLOW)
        area_label.next_to(integral_axes, UP, buff=0.18)
        check_equations = VGroup(
            MathTex(r"\\Gamma(1)=1", font_size=31, color=YELLOW),
            MathTex(r"\\Gamma(2)=1", font_size=31, color=YELLOW),
            MathTex(r"\\Gamma(3)=2", font_size=31, color=YELLOW),
            MathTex(r"\\Gamma(5)=24=4!", font_size=31, color=YELLOW),
            MathTex(r"\\Gamma(1/2)=\\sqrt{\\pi}", font_size=31, color=BLUE),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        check_equations.to_edge(RIGHT, buff=0.55)
        criteria = VGroup(
            Text("match factorial dots", font_size=20, color=YELLOW),
            Text("obey the step rule", font_size=20, color=YELLOW),
            Text("avoid arbitrary wiggles", font_size=20, color=YELLOW),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.18)
        criteria.to_edge(RIGHT, buff=0.26).shift(UP * 0.82)
        unlocks = VGroup(
            Text("probability", font_size=20, color=BLUE),
            Text("asymptotics", font_size=20, color=BLUE),
            Text("complex analysis", font_size=20, color=BLUE),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        unlocks.next_to(criteria, DOWN, buff=0.42)
        visual = VGroup(factorial_axes, gamma_curve, factorial_dots)
        visual.move_to(ORIGIN)
'''
        if 'fourier' in lowered:
            return '''        axes = Axes(
            x_range=[-PI, PI, PI / 2],
            y_range=[-1.8, 1.8, 1],
            x_length=8.4,
            y_length=4.1,
            tips=False,
        )
        first_wave = axes.plot(lambda x: math.sin(x), x_range=[-PI, PI], color=BLUE)
        harmonic_wave = axes.plot(
            lambda x: math.sin(x) + math.sin(3 * x) / 3 + math.sin(5 * x) / 5,
            x_range=[-PI, PI],
            color=YELLOW,
        )
        target = VGroup(
            Line(axes.c2p(-PI, -1), axes.c2p(0, -1), color=GREEN),
            Line(axes.c2p(0, 1), axes.c2p(PI, 1), color=GREEN),
            DashedLine(axes.c2p(0, -1), axes.c2p(0, 1), color=GREEN),
        )
        component_label = Text("component waves", font_size=24, color=GREY_B)
        component_label.next_to(axes, DOWN, buff=0.22)
        visual = VGroup(axes, first_wave, harmonic_wave, target, component_label)
        visual.move_to(ORIGIN).shift(DOWN * 0.08)
'''
        if domain == 'calculus':
            return '''        h_tracker = ValueTracker(1.3)
        base_x = 0.8

        def y_value(x):
            return 0.45 * (x - 0.35) ** 2 + 0.35

        axes = Axes(
            x_range=[-1, 3, 1],
            y_range=[-0.5, 4, 1],
            x_length=7.6,
            y_length=4.25,
            tips=False,
        )
        curve = axes.plot(y_value, x_range=[-0.7, 2.8], color=BLUE)
        base = Dot(axes.c2p(base_x, y_value(base_x)), color=YELLOW)
        moving = always_redraw(
            lambda: Dot(
                axes.c2p(base_x + h_tracker.get_value(), y_value(base_x + h_tracker.get_value())),
                color=GREEN,
            )
        )
        secant = always_redraw(lambda: Line(base.get_center(), moving.get_center(), color=GREEN))
        h_label = always_redraw(
            lambda: Text(f"h = {h_tracker.get_value():.2f}", font_size=22, color=YELLOW)
            .next_to(moving, UR, buff=0.14)
        )
        tangent = Line(axes.c2p(0.02, 0.16), axes.c2p(1.84, 1.88), color=YELLOW)
        slope_label = Text("local slope", font_size=24, color=YELLOW)
        slope_label.move_to(axes.c2p(1.72, 2.1))
        height_line = DashedLine(
            axes.c2p(base_x, 0),
            axes.c2p(base_x, y_value(base_x)),
            color=GREY_B,
        )
        height_label = Text("height", font_size=21, color=GREY_B)
        height_label.next_to(height_line, DOWN, buff=0.12).shift(LEFT * 0.18)
        slope_arrow = Arrow(
            axes.c2p(0.55, 0.55),
            axes.c2p(1.45, 1.4),
            buff=0,
            color=YELLOW,
            stroke_width=5,
        )
        derivative_formula = MathTex(
            r"f'(x)=\\lim_{h\\to 0}\\frac{f(x+h)-f(x)}{h}",
            font_size=33,
            color=YELLOW,
        )
        derivative_formula.to_edge(DOWN, buff=0.45)
        example = VGroup(
            MathTex(r"f(x)=x^2", font_size=30, color=GREY_B),
            MathTex(r"\\frac{(3+h)^2-9}{h}=6+h", font_size=31, color=YELLOW),
            MathTex(r"h\\to0\\quad\\Rightarrow\\quad f'(3)=6", font_size=31, color=YELLOW),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        example.to_corner(DR, buff=0.55)
        visual = VGroup(axes, curve)
        visual.move_to(ORIGIN).shift(DOWN * 0.05)
'''
        if domain == 'linear_algebra':
            return '''        matrix_a = Matrix([["1", "2"], ["3", "4"]]).scale(0.72).set_color(BLUE)
        times = MathTex(r"\\times", font_size=38)
        matrix_b = Matrix([["5", "6"], ["7", "8"]]).scale(0.72).set_color(GREEN)
        equals = MathTex("=", font_size=38)
        result = Matrix([["19", "22"], ["43", "50"]]).scale(0.72).set_color(YELLOW)
        group = VGroup(matrix_a, times, matrix_b, equals, result).arrange(RIGHT, buff=0.25)
        row_box = SurroundingRectangle(matrix_a.get_rows()[0], color=YELLOW, buff=0.06)
        col_box = SurroundingRectangle(matrix_b.get_columns()[0], color=YELLOW, buff=0.06)
        entry_box = SurroundingRectangle(result.get_entries()[0], color=YELLOW, buff=0.08)
        formula = Text("c11 = 1*5 + 2*7 = 19", font_size=28, color=YELLOW)
        formula.next_to(group, DOWN, buff=0.35)
        visual = VGroup(group)
        visual.move_to(ORIGIN)
'''
        if domain == 'complex_analysis' or 'euler' in lowered:
            return '''        theta = ValueTracker(0)
        circle = Circle(radius=1.85, color=BLUE)
        real_axis = Line(LEFT * 2.25, RIGHT * 2.25, color=GREY)
        imag_axis = Line(DOWN * 2.25, UP * 2.25, color=GREY)
        point = always_redraw(
            lambda: Dot(circle.point_at_angle(theta.get_value()), color=YELLOW)
        )
        radius = always_redraw(
            lambda: Arrow(ORIGIN, point.get_center(), buff=0, color=YELLOW)
        )
        angle_label = always_redraw(
            lambda: Text(f"t = {theta.get_value():.2f}", font_size=23, color=YELLOW)
            .next_to(circle, DOWN, buff=0.18)
        )
        coordinate_label = MathTex(r"(-1,0)", font_size=36, color=YELLOW)
        coordinate_label.next_to(circle, RIGHT, buff=0.35)
        identity = MathTex(r"e^{i\\pi} + 1 = 0", font_size=42, color=YELLOW)
        identity.next_to(circle, DOWN, buff=0.45)
        visual = VGroup(circle, real_axis, imag_axis, radius, point)
        visual.move_to(ORIGIN).shift(UP * 0.08)
'''
        return '''        source = Circle(radius=1.0, color=BLUE)
        operation = Arrow(LEFT * 1.4, RIGHT * 1.4, color=YELLOW)
        target = Square(side_length=1.55, color=GREEN).next_to(operation, RIGHT, buff=0.5)
        source.next_to(operation, LEFT, buff=0.45)
        invariant = Text("invariant", font_size=24, color=YELLOW).next_to(operation, UP)
        visual = VGroup(source, operation, target, invariant)
        visual.move_to(ORIGIN)
'''

    def _visual_action_code(self, domain: str, concept: str, beat: StoryboardBeat) -> str:
        lowered = concept.lower()
        if 'gamma' in lowered:
            if beat.index == 1:
                return '''        self.play(Create(factorial_axes), FadeIn(axis_labels), run_time=1.5)
        self.play(LaggedStart(*[FadeIn(dot) for dot in factorial_dots], lag_ratio=0.18), run_time=1.5)
        self.play(LaggedStart(*[Write(label) for label in factorial_labels], lag_ratio=0.12), run_time=1.8)
        self.play(Write(question), run_time=1.5)
'''
            if beat.index == 2:
                return '''        self.play(Create(factorial_axes), FadeIn(axis_labels), run_time=1.0)
        self.play(FadeIn(factorial_dots), FadeIn(factorial_labels), run_time=1.0)
        self.play(Create(gamma_curve), run_time=2.6)
        self.play(Write(recurrence), run_time=1.2)
        self.play(LaggedStart(*[GrowArrow(arrow) for arrow in ladder_arrows], lag_ratio=0.18), run_time=2.0)
        self.play(Circumscribe(recurrence), run_time=1.1)
'''
            if beat.index == 3:
                return '''        self.play(Create(integral_axes), run_time=1.2)
        self.play(Create(integrand), run_time=1.6)
        self.play(FadeIn(area), run_time=1.2)
        self.play(Write(integral_formula), FadeIn(area_label), run_time=1.8)
        self.play(Indicate(area, color=YELLOW), run_time=1.4)
'''
            if beat.index == 4:
                return '''        self.play(Create(factorial_axes), FadeIn(axis_labels), run_time=1.0)
        self.play(FadeIn(factorial_dots), Create(gamma_curve), run_time=1.7)
        self.play(Write(check_equations), run_time=2.6)
        self.play(LaggedStart(*[Indicate(dot, color=YELLOW) for dot in factorial_dots], lag_ratio=0.18), run_time=2.2)
'''
            if beat.index == 5:
                return '''        self.play(Create(factorial_axes), FadeIn(axis_labels[1]), run_time=0.9)
        self.play(FadeIn(factorial_dots), Create(gamma_curve), run_time=1.4)
        self.play(Create(alternative_curve), run_time=1.6)
        self.play(FadeIn(criteria), run_time=1.8)
        self.play(Indicate(alternative_curve, color=RED), Indicate(criteria[2], color=YELLOW), run_time=1.6)
        self.play(FadeIn(unlocks), run_time=1.3)
'''
            return '''        self.play(Create(factorial_axes), FadeIn(axis_labels), run_time=1.0)
        self.play(FadeIn(factorial_dots), Create(gamma_curve), Write(recurrence), run_time=2.4)
'''
        if 'fourier' in lowered:
            return '''        self.play(Create(axes), run_time=1.4)
        self.play(Create(target), run_time=1.4)
        self.play(Create(first_wave), run_time=2.4)
        self.play(Transform(first_wave.copy(), harmonic_wave), run_time=3.0)
'''
        if domain == 'calculus':
            if beat.index == 1:
                return '''        self.play(Create(axes), Create(curve), run_time=2.0)
        self.play(FadeIn(base), FadeIn(moving), Create(secant), FadeIn(h_label), run_time=1.8)
        self.play(h_tracker.animate.set_value(0.72), run_time=3.2, rate_func=linear)
'''
            if beat.index == 2:
                return '''        self.play(Create(axes), Create(curve), run_time=1.4)
        self.play(FadeIn(base), FadeIn(moving), Create(secant), FadeIn(h_label), run_time=1.2)
        self.play(h_tracker.animate.set_value(0.16), run_time=6.4, rate_func=linear)
'''
            if beat.index == 3:
                return '''        self.play(Create(axes), Create(curve), run_time=1.4)
        self.play(FadeIn(base), FadeIn(moving), Create(secant), FadeIn(h_label), run_time=1.1)
        self.play(h_tracker.animate.set_value(0.16), run_time=4.6, rate_func=linear)
        self.play(FadeOut(h_label), run_time=0.35)
        self.play(Create(tangent), FadeIn(slope_label), FadeIn(derivative_formula), run_time=2.0)
'''
            if beat.index == 4:
                return '''        self.play(Create(axes), Create(curve), run_time=1.5)
        self.play(FadeIn(base), run_time=0.6)
        self.play(FadeIn(example), Circumscribe(base), run_time=2.4)
        self.play(Create(tangent), FadeIn(slope_label), run_time=1.5)
'''
            if beat.index == 5:
                return '''        self.play(Create(axes), Create(curve), run_time=0.9)
        self.play(FadeIn(base), Create(height_line), FadeIn(height_label), run_time=1.4)
        self.play(Create(slope_arrow), Create(tangent), FadeIn(slope_label), run_time=2.0)
        self.play(Indicate(height_label, color=GREY_B), Indicate(slope_label, color=YELLOW), run_time=1.5)
'''
            return '''        self.play(Create(axes), Create(curve), run_time=2.0)
        self.play(FadeIn(base), FadeIn(moving), Create(secant), FadeIn(h_label), run_time=1.4)
        self.play(h_tracker.animate.set_value(0.16), run_time=5.4, rate_func=linear)
        self.play(Create(tangent), FadeIn(slope_label), FadeIn(height_label), run_time=1.4)
'''
        if domain == 'linear_algebra':
            return '''        self.play(FadeIn(group), run_time=2.0)
        self.play(Create(row_box), Create(col_box), run_time=1.8)
        self.play(Write(formula), run_time=2.2)
        self.play(Create(entry_box), run_time=1.2)
'''
        if domain == 'complex_analysis' or 'euler' in lowered:
            return '''        self.play(Create(circle), Create(real_axis), Create(imag_axis), run_time=2.0)
        self.play(FadeIn(point), Create(radius), FadeIn(angle_label), run_time=1.2)
        self.play(theta.animate.set_value(PI), run_time=5.2, rate_func=linear)
        self.play(FadeIn(coordinate_label), Write(identity), run_time=1.8)
'''
        return '''        self.play(FadeIn(source), run_time=1.0)
        self.play(GrowArrow(operation), run_time=1.5)
        self.play(FadeIn(target), Write(invariant), run_time=2.0)
        self.play(Circumscribe(invariant), run_time=1.2)
'''
