"""
Manim Scene Generator.

Takes a math concept description and generates Manim Python code.

The generator uses template-based generation for known concepts and
LLM-assisted generation for novel ones. Templates are organized by
mathematical domain (algebra, calculus, linear algebra, etc.).

Each generated scene follows the Manim Community pattern:
  - A class inheriting from Scene (or MovingCameraScene, etc.)
  - A construct() method with self.play() calls
  - Clean resource management
"""
from __future__ import annotations

import ast
import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import ClassVar

logger = logging.getLogger(__name__)


def _env_or_setting(
    name: str,
    default: str | None = None,
    aliases: tuple[str, ...] = (),
) -> str | None:
    """Read config from the environment, then optional Django settings."""
    for key in (name, *aliases):
        value = os.environ.get(key)
        if value:
            return value

    try:
        from django.conf import settings

        if settings.configured:
            for key in (name, *aliases):
                setting_value = getattr(settings, key, None)
                if setting_value:
                    return str(setting_value)
    except Exception:
        return default

    return default


def _float_env_or_setting(
    name: str,
    default: float,
    aliases: tuple[str, ...] = (),
) -> float:
    """Read a float config value from the environment, then optional Django settings."""
    raw_value = _env_or_setting(name, aliases=aliases)
    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except (TypeError, ValueError):
        logger.warning('Invalid %s value %r; using %s', name, raw_value, default)
        return default


# ─── Scene templates organized by domain ────────────────────────────────────

SCENE_TEMPLATES: dict[str, dict] = {
    'eulers-identity': {
        'name': 'EulersIdentity',
        'base_class': 'Scene',
        'description': "Visual proof of e^(iπ) = -1 using the unit circle",
        'template': '''
from manim import *

class EulersIdentity(Scene):
    def construct(self):
        # Title
        title = MathTex(r"e^{i\\pi} = -1", font_size=72)
        title.to_edge(UP)
        step = Text("Step 1: complex exponentials rotate", font_size=28).to_edge(DOWN)
        self.play(Write(title), FadeIn(step))
        self.wait(1)

        # Unit circle
        circle = Circle(radius=2, color=BLUE)
        axes = Axes(x_range=[-3, 3], y_range=[-3, 3], x_length=6, y_length=6)
        self.play(Create(axes), Create(circle))
        self.wait(1)

        # Point on circle: angle pi
        angle_tracker = ValueTracker(0)
        dot = always_redraw(
            lambda: Dot(
                point=axes.c2p(
                    2 * np.cos(angle_tracker.get_value()),
                    2 * np.sin(angle_tracker.get_value())
                ),
                color=YELLOW
            )
        )
        label = always_redraw(
            lambda: Text(
                f"({{2 * np.cos(angle_tracker.get_value()):.2f}}, "
                f"{{2 * np.sin(angle_tracker.get_value()):.2f}})",
                font_size=28
            ).next_to(dot, UR, buff=0.2)
        )
        angle_label = always_redraw(
            lambda: MathTex(
                rf"t = {angle_tracker.get_value():.2f}",
                font_size=34
            ).to_corner(UL)
        )

        self.play(FadeIn(dot), FadeIn(label), Write(angle_label))
        self.play(
            Transform(step, Text("Step 2: move halfway around the unit circle", font_size=28).to_edge(DOWN))
        )
        self.play(angle_tracker.animate.set_value(PI), run_time=5)
        self.wait(1)

        # Show e^(i*pi) = -1
        self.play(
            Transform(step, Text("Step 3: read the final coordinates", font_size=28).to_edge(DOWN))
        )
        result = MathTex(
            r"e^{i\\pi}",
            "=",
            r"\\cos(\\pi) + i\\sin(\\pi)",
            "=",
            "-1",
            font_size=42,
        )
        result.to_edge(DOWN)
        coord = MathTex(r"(\\cos \\pi, \\sin \\pi)=(-1, 0)", font_size=40).next_to(title, DOWN)
        self.play(Write(coord))
        self.wait(1)
        self.play(ReplacementTransform(coord, result), FadeOut(step))
        self.wait(3)
''',
    },
    'derivative-definition': {
        'name': 'DerivativeDefinition',
        'base_class': 'Scene',
        'description': "Animated limit definition of the derivative",
        'template': '''
from manim import *

class DerivativeDefinition(Scene):
    def construct(self):
        title = MathTex(r"f'(x) = \\lim_{h \\to 0} \\frac{f(x+h) - f(x)}{h}", font_size=44)
        title.to_edge(UP)
        step = Text("Step 1: start with an average rate of change", font_size=28).to_edge(DOWN)
        self.play(Write(title), FadeIn(step))

        # Axes
        axes = Axes(
            x_range=[-1, 8], y_range=[-1, 8],
            x_length=10, y_length=6,
            axis_config={"include_tip": True}
        ).shift(DOWN * 0.5)
        labels = axes.get_axis_labels("x", "f(x)")
        self.play(Create(axes), Write(labels))

        # Function curve
        curve = axes.plot(lambda x: 0.5 * x**2 - x + 2, color=BLUE)
        curve_label = MathTex(r"f(x) = \\frac{1}{2}x^2 - x + 2", font_size=36).to_edge(UR)
        self.play(Create(curve), Write(curve_label))

        # Point on curve
        func = lambda x: 0.5 * x**2 - x + 2
        x_val = 3
        point = axes.c2p(x_val, func(x_val))
        dot = Dot(point, color=YELLOW)

        # Secant line (h shrinking)
        h_tracker = ValueTracker(3)
        moving_dot = always_redraw(
            lambda: Dot(
                axes.c2p(x_val + h_tracker.get_value(), func(x_val + h_tracker.get_value())),
                color=ORANGE
            )
        )
        secant = always_redraw(
            lambda: Line(
                axes.c2p(x_val, func(x_val)),
                axes.c2p(x_val + h_tracker.get_value(), func(x_val + h_tracker.get_value())),
                color=RED
            )
        )
        h_label = always_redraw(
            lambda: MathTex(rf"h={h_tracker.get_value():.2f}", font_size=34).to_corner(UR)
        )
        quotient = always_redraw(
            lambda: MathTex(
                rf"\\frac{{f(x+h)-f(x)}}{{h}} \\approx {2 + 0.5 * h_tracker.get_value():.2f}",
                font_size=34
            ).next_to(step, UP)
        )
        self.play(FadeIn(dot), FadeIn(moving_dot), Create(secant), Write(h_label), Write(quotient))
        self.wait(1)

        # Animate h → 0
        self.play(
            Transform(step, Text("Step 2: shrink h and watch the secant settle", font_size=28).to_edge(DOWN))
        )
        self.play(h_tracker.animate.set_value(0.01), run_time=6)
        tangent = Line(
            axes.c2p(x_val - 1.5, func(x_val) - 2 * 1.5),
            axes.c2p(x_val + 1.5, func(x_val) + 2 * 1.5),
            color=YELLOW,
        )
        conclusion = Text("Step 3: the limiting slope is the derivative", font_size=28).to_edge(DOWN)
        slope_label = MathTex(r"f'(3)=2", font_size=42).next_to(dot, UL)
        self.play(Transform(step, conclusion), ReplacementTransform(secant, tangent), Write(slope_label))
        self.wait(3)
''',
    },
    'matrix-multiplication': {
        'name': 'MatrixMultiplication',
        'base_class': 'Scene',
        'description': "Animated matrix multiplication with element highlighting",
        'template': '''
from manim import *

class MatrixMultiplication(Scene):
    def construct(self):
        title = Text("Matrix multiplication: rows meet columns", font_size=36).to_edge(UP)
        step = Text("Step 1: set up A, B, and the result", font_size=28).to_edge(DOWN)
        self.play(Write(title), FadeIn(step))

        # Define matrices
        A = Matrix([["1", "2"], ["3", "4"]]).set_color(BLUE)
        A_label = MathTex("A", font_size=48).next_to(A, UP)

        times = MathTex(r"\\times", font_size=48).next_to(A, RIGHT)

        B = Matrix([["5", "6"], ["7", "8"]]).set_color(GREEN)
        B_label = MathTex("B", font_size=48).next_to(B, UP)
        B.next_to(times, RIGHT)

        equals = MathTex(r"=", font_size=48)

        C = Matrix([["19", "22"], ["43", "50"]]).set_color(YELLOW)
        C_label = MathTex("C = AB", font_size=48).next_to(C, UP)
        C.next_to(equals, RIGHT)
        equals.next_to(B, RIGHT)

        group = VGroup(A, A_label, times, B, B_label, equals, C, C_label)
        group.move_to(ORIGIN)

        self.play(Write(A), Write(A_label), run_time=1.5)
        self.play(Write(times), run_time=0.8)
        self.play(Write(B), Write(B_label), run_time=1.5)
        self.wait(1)
        self.play(
            Transform(step, Text("Step 2: each result entry is one row dot one column", font_size=28).to_edge(DOWN))
        )
        self.play(Write(equals), Write(C), Write(C_label), run_time=1.5)
        self.wait(1)

        # Show computation step
        computations = [
            MathTex(r"c_{11} = 1 \\times 5 + 2 \\times 7 = 19", font_size=34),
            MathTex(r"c_{12} = 1 \\times 6 + 2 \\times 8 = 22", font_size=34),
            MathTex(r"c_{21} = 3 \\times 5 + 4 \\times 7 = 43", font_size=34),
            MathTex(r"c_{22} = 3 \\times 6 + 4 \\times 8 = 50", font_size=34),
        ]
        current = computations[0].next_to(group, DOWN, buff=0.6)
        self.play(Write(current), run_time=1.5)
        self.wait(1)
        for expression in computations[1:]:
            expression.next_to(group, DOWN, buff=0.6)
            self.play(ReplacementTransform(current, expression), run_time=1.5)
            current = expression
            self.wait(1)
        self.play(
            Transform(step, Text("Step 3: repeat the row-column rule for every entry", font_size=28).to_edge(DOWN))
        )
        self.wait(3)
''',
    },
    'fourier-series': {
        'name': 'FourierSeriesSquare',
        'base_class': 'Scene',
        'description': "Fourier series approximation of a square wave",
        'template': '''
from manim import *

class FourierSeriesSquare(Scene):
    def construct(self):
        title = Text("Fourier Series: Square Wave Approximation", font_size=38)
        title.to_edge(UP)
        step = Text("Step 1: target a repeating square wave", font_size=28).to_edge(DOWN)
        self.play(Write(title), FadeIn(step))

        axes = Axes(
            x_range=[-2 * PI, 2 * PI, PI],
            y_range=[-2, 2],
            x_length=10, y_length=4,
            tips=False
        ).shift(DOWN * 0.5)

        self.play(Create(axes))

        # Square wave reference
        square_wave = axes.plot(
            lambda x: 1 if (x % (2 * PI)) < PI else -1,
            color=GREY_B, stroke_width=1
        )
        self.play(Create(square_wave))
        self.wait(1)

        # Fourier approximation with increasing terms
        n_terms_tracker = ValueTracker(1)

        fourier_curve = always_redraw(
            lambda: axes.plot(
                lambda x: sum(
                    (4 / (2 * k + 1) / PI) * np.sin((2 * k + 1) * x)
                    for k in range(int(n_terms_tracker.get_value()))
                ),
                color=YELLOW, stroke_width=2
            )
        )

        terms_label = always_redraw(
            lambda: Text(
                f"n = {int(n_terms_tracker.get_value())} terms",
                font_size=30
            ).to_edge(DR)
        )

        self.play(Create(fourier_curve), Write(terms_label))
        self.play(
            Transform(step, Text("Step 2: add low frequencies first", font_size=28).to_edge(DOWN)),
            n_terms_tracker.animate.set_value(3),
            run_time=3,
            rate_func=linear,
        )
        self.wait(1)
        self.play(
            Transform(step, Text("Step 3: odd harmonics sharpen the jumps", font_size=28).to_edge(DOWN)),
            n_terms_tracker.animate.set_value(8),
            run_time=4,
            rate_func=linear,
        )
        self.wait(1)
        self.play(
            Transform(step, Text("Step 4: more terms improve the approximation", font_size=28).to_edge(DOWN)),
            n_terms_tracker.animate.set_value(20),
            run_time=6,
            rate_func=linear,
        )
        self.wait(3)
''',
    },
}

# ─── Concept → domain mapping ────────────────────────────────────────────────

CONCEPT_DOMAINS: dict[str, list[str]] = {
    'calculus': [
        'derivative',
        'integral',
        'limit',
        'series',
        'taylor',
        'fourier',
        'differentiation',
        'integration',
        'continuity',
        'epsilon',
    ],
    'linear_algebra': [
        'matrix',
        'vector',
        'eigenvalue',
        'eigenvector',
        'determinant',
        'linear transformation',
        'basis',
        'span',
        'null space',
        'rank',
    ],
    'complex_analysis': [
        'euler',
        'complex',
        'imaginary',
        'polar',
        'conformal',
        'residue',
        'cauchy',
    ],
    'topology': ['topology', 'manifold', 'homotopy', 'homology', 'knot', 'morse', 'borsuk'],
    'number_theory': [
        'prime',
        'modular',
        'congruence',
        'fermat',
        'riemann zeta',
        'goldbach',
        'twin prime',
    ],
    'probability': [
        'probability',
        'distribution',
        'bayes',
        'random',
        'expectation',
        'variance',
        'markov',
        'poisson',
        'gaussian',
        'central limit',
    ],
    'geometry': [
        'circle',
        'triangle',
        'polygon',
        'conic',
        'ellipse',
        'hyperbola',
        'pythagorean',
        'euclidean',
        'non-euclidean',
    ],
    'algebra': [
        'group',
        'ring',
        'field',
        'isomorphism',
        'homomorphism',
        'abelian',
        'galois',
        'polynomial',
        'abstract algebra',
    ],
}

# ─── Scene generator ─────────────────────────────────────────────────────────

@dataclass
class GeneratedScene:
    """Result of scene generation."""
    concept: str
    scene_name: str
    scene_code: str
    base_class: str = 'Scene'
    description: str = ''
    source: str = 'template'  # 'template', 'llm', or 'placeholder'
    metadata: dict = field(default_factory=dict)


def _scene_name_from_concept(concept: str) -> str:
    """Create a safe Manim scene class name from free-form text."""
    scene_name = re.sub(r'[^a-zA-Z0-9]', '', concept.title())[:40] or 'CustomScene'
    if not scene_name.endswith('Scene'):
        scene_name += 'Scene'
    if scene_name[0].isdigit():
        scene_name = f'Concept{scene_name}'
    return scene_name


def _build_placeholder_scene(concept: str, scene_name: str, domain: str) -> str:
    """Generate a minimal, valid Manim scene for graceful degradation."""
    concept_literal = repr(concept)
    domain_literal = repr(domain)
    return f'''
from manim import *

class {scene_name}(Scene):
    """Fallback Manim scene."""
    def construct(self):
        concept = {concept_literal}
        domain = {domain_literal}

        title = Text(concept, font_size=42)
        title.to_edge(UP)
        self.play(Write(title))
        self.wait(1)

        steps = [
            "1. Name the object",
            "2. Show the operation",
            "3. Track what changes",
            "4. Mark what stays meaningful",
            "5. State the takeaway",
        ]
        step_group = VGroup(
            *[Text(step, font_size=30) for step in steps]
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
        step_group.move_to(ORIGIN)

        domain_label = Text(f"Domain: {domain}", font_size=28, color=GREY).to_edge(DOWN)
        self.play(FadeIn(domain_label))
        for step_text in step_group:
            self.play(Write(step_text), run_time=0.8)
            self.wait(0.6)
        box = SurroundingRectangle(step_group, color=YELLOW, buff=0.25)
        self.play(Create(box))
        self.wait(2)
'''.strip()


@dataclass
class LLMSceneGenerator:
    """Generate Manim scene code with an LLM and validate the result.

    Provider selection intentionally mirrors the app runtime:
      - OpenAI when OPENAI_API_KEY is configured
      - Ollama otherwise

    Every public generation path falls back to a placeholder scene. Callers
    should never need to catch provider or validation errors to get valid code.
    """

    model: str | None = None
    timeout: int = 30
    temperature: float = field(
        default_factory=lambda: _float_env_or_setting(
            'MANIM_SCENE_TEMPERATURE',
            0.3,
            # Backward compatibility for the pre-migration misspelling.
            aliases=('MANIN_SCENE_TEMPERATURE',),
        )
    )
    provider: str = field(init=False)

    DEFAULT_OPENAI_MODEL: ClassVar[str] = 'gpt-4o-mini'
    DEFAULT_OLLAMA_MODEL: ClassVar[str] = 'deepseek-v4-pro'

    SYSTEM_PROMPT: ClassVar[str] = """
You generate concise, valid Manim Community Edition scene code.

Available Manim classes and helpers:
- Scene, ThreeDScene
- Circle, Square, Rectangle, Axes, NumberPlane
- Text, Tex, MathTex, Matrix, VGroup, VDict
- Dot, Arrow, Line, CurvedArrow, Arc, Annulus, Brace, SurroundingRectangle
- ValueTracker, always_redraw

Available animations:
- Write, Create, FadeIn, FadeOut
- Transform, ReplacementTransform, MoveTo, Rotate, Scale
- GrowFromCenter, ShrinkToCenter, DrawBorderThenFill
- Indicate, Flash, Circumscribe, Wiggle

Camera methods:
- move_camera(...)
- camera.frame.animate.scale(...)
- camera.frame.animate.move_to(...)

Plain English labels can use Text(); mathematical notation should usually use
Tex() or MathTex(). Keep scenes short, deterministic, and free of external
assets.
""".strip()

    FEW_SHOT_EXAMPLES: ClassVar[tuple[str, str, str]] = (
        """
Concept: limit definition of the derivative
Domain: calculus
```python
from manim import *

class LimitDefinitionScene(Scene):
    def construct(self):
        title = MathTex(r"f'(a)=\\lim_{h\\to0}\\frac{f(a+h)-f(a)}{h}")
        title.to_edge(UP)
        axes = Axes(x_range=[-1, 5], y_range=[-1, 7], x_length=7, y_length=4)
        curve = axes.plot(lambda x: 0.35 * x * x + 1, color=BLUE)
        a = 2
        h = ValueTracker(2)
        moving_dot = always_redraw(
            lambda: Dot(axes.c2p(a + h.get_value(), 0.35 * (a + h.get_value()) ** 2 + 1))
        )
        base_dot = Dot(axes.c2p(a, 0.35 * a * a + 1), color=YELLOW)
        secant = always_redraw(
            lambda: Line(
                base_dot.get_center(),
                moving_dot.get_center(),
                color=RED,
            ).set_length(4)
        )
        label = always_redraw(lambda: MathTex(f"h={h.get_value():.2f}").to_edge(DOWN))
        self.play(Write(title), Create(axes), Create(curve))
        self.play(FadeIn(base_dot), FadeIn(moving_dot), Create(secant), Write(label))
        self.play(h.animate.set_value(0.05), run_time=3)
        self.play(Indicate(base_dot))
        self.wait(1)
```
""".strip(),
        """
Concept: Pythagorean theorem visual proof
Domain: geometry
```python
from manim import *

class PythagoreanProofScene(Scene):
    def construct(self):
        title = MathTex(r"a^2+b^2=c^2").to_edge(UP)
        p1 = ORIGIN
        p2 = 3 * RIGHT
        p3 = 3 * RIGHT + 2 * UP
        triangle = VGroup(Line(p1, p2), Line(p2, p3), Line(p3, p1)).set_color(WHITE)
        triangle.move_to(ORIGIN)
        a_square = Square(side_length=2, color=BLUE).next_to(triangle, LEFT, buff=0.15)
        b_square = Square(side_length=3, color=GREEN).next_to(triangle, DOWN, buff=0.15)
        c_square = Square(side_length=3.6, color=YELLOW).next_to(triangle, UR, buff=0.15)
        labels = VGroup(
            MathTex("a^2").move_to(a_square),
            MathTex("b^2").move_to(b_square),
            MathTex("c^2").move_to(c_square),
        )
        self.play(Write(title))
        self.play(Create(triangle), DrawBorderThenFill(a_square))
        self.play(DrawBorderThenFill(b_square), DrawBorderThenFill(c_square))
        self.play(Write(labels))
        self.play(Circumscribe(VGroup(a_square, b_square)), Flash(c_square))
        self.wait(1)
```
""".strip(),
        """
Concept: eigenvectors under a linear transformation
Domain: linear algebra
```python
from manim import *

class EigenvectorScene(Scene):
    def construct(self):
        plane = NumberPlane(x_range=[-4, 4], y_range=[-3, 3])
        title = Text("Eigenvectors keep their direction", font_size=34).to_edge(UP)
        matrix = [[2, 0], [0, 0.5]]
        vector = Arrow(ORIGIN, RIGHT + UP, buff=0, color=YELLOW)
        eigen = Arrow(ORIGIN, 2 * RIGHT, buff=0, color=GREEN)
        transformed_vector = vector.copy().apply_matrix(matrix)
        transformed_eigen = eigen.copy().apply_matrix(matrix)
        labels = VGroup(
            MathTex(r"v").next_to(vector.get_end(), UP),
            MathTex(r"Av").next_to(transformed_vector.get_end(), UP),
            MathTex(r"e").next_to(eigen.get_end(), DOWN),
            MathTex(r"Ae").next_to(transformed_eigen.get_end(), DOWN),
        )
        self.play(Create(plane), Write(title))
        self.play(Create(vector), Create(eigen), Write(labels[0]), Write(labels[2]))
        self.play(Transform(vector, transformed_vector), Transform(eigen, transformed_eigen))
        self.play(ReplacementTransform(labels[0], labels[1]))
        self.play(ReplacementTransform(labels[2], labels[3]), Wiggle(eigen))
        self.wait(1)
```
""".strip(),
    )

    def __post_init__(self) -> None:
        self.provider = self._detect_provider()
        env_model = _env_or_setting('MANIM_SCENE_MODEL', aliases=('MANIN_SCENE_MODEL',))
        if not self.model:
            self.model = env_model or self._default_model()

    def _detect_provider(self) -> str:
        """Detect the active LLM provider from configured credentials."""
        if _env_or_setting('OPENAI_API_KEY'):
            return 'openai'
        return 'ollama'

    def _default_model(self) -> str:
        if self.provider == 'openai':
            return self.DEFAULT_OPENAI_MODEL
        return self.DEFAULT_OLLAMA_MODEL

    def generate(
        self,
        concept: str,
        context: dict | None = None,
        scene_name: str | None = None,
        domain: str = 'general',
    ) -> GeneratedScene:
        """Generate and validate scene code, falling back on any failure."""
        context = context or {}
        scene_name = scene_name or _scene_name_from_concept(concept)

        try:
            prompt = self._build_prompt(concept, context, scene_name, domain)
            response = self._call_llm(prompt)
            scene_code = self.extract_python_code(response)
            validation_error = self.validate_scene_code(scene_code)
            if validation_error:
                raise ValueError(validation_error)

            parsed_scene_name = self.extract_scene_name(scene_code) or scene_name
            return GeneratedScene(
                concept=concept,
                scene_name=parsed_scene_name,
                scene_code=scene_code,
                base_class='Scene',
                description=f'LLM-generated scene for: {concept}',
                source='llm',
                metadata={
                    'domain': domain,
                    'provider': self.provider,
                    'model': self.model,
                },
            )
        except Exception as exc:
            logger.warning('LLM scene generation failed for %r: %s', concept, exc)
            return self._placeholder_result(concept, scene_name, domain, str(exc))

    def _placeholder_result(
        self,
        concept: str,
        scene_name: str,
        domain: str,
        reason: str,
    ) -> GeneratedScene:
        return GeneratedScene(
            concept=concept,
            scene_name=scene_name,
            scene_code=_build_placeholder_scene(concept, scene_name, domain),
            base_class='Scene',
            description=f'Fallback scene for: {concept}',
            source='placeholder',
            metadata={
                'domain': domain,
                'provider': self.provider,
                'model': self.model,
                'fallback_reason': reason[:500],
            },
        )

    def _build_prompt(
        self,
        concept: str,
        context: dict,
        scene_name: str,
        domain: str,
    ) -> str:
        context_text = ''
        if context:
            context_text = json.dumps(context, default=str)[:1200]

        few_shots = '\n\n'.join(self.FEW_SHOT_EXAMPLES)

        return f"""
{self.SYSTEM_PROMPT}

Use these examples as style and API references:

{few_shots}

Generate Manim Community Edition Python code for this math animation.

Concept description:
{concept}

Mathematical domain:
{domain}

Session context:
{context_text or '(none)'}

Required scene class name:
{scene_name}

Rules:
- Return one Python code block only.
- The code must start with `from manim import *`.
- Define exactly one primary scene class named {scene_name}.
- The scene must include `def construct(self):`.
- Build a 25-45 second explanatory scene with 4-6 visible steps.
- Use step labels or short captions so the viewer can follow the concept.
- Prefer a concrete example over an abstract-only animation.
- Keep rendering practical without external assets.
- Use valid Python and valid Manim Community Edition APIs.
- Prefer Text() for plain labels when Tex()/MathTex() is unnecessary.
""".strip()

    def _call_llm(self, prompt: str) -> str:
        if self.provider == 'openai':
            return self._call_openai(prompt)
        return self._call_ollama(prompt)

    def _post_json(
        self,
        url: str,
        payload: dict,
        headers: dict[str, str] | None = None,
    ) -> dict:
        request_headers = {'Content-Type': 'application/json'}
        if headers:
            request_headers.update(headers)

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=request_headers,
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'HTTP {exc.code}: {body[:500]}') from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc

    def _call_openai(self, prompt: str) -> str:
        api_key = _env_or_setting('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError('OPENAI_API_KEY is not configured')

        base_url = _env_or_setting('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
        data = self._post_json(
            f'{base_url}/chat/completions',
            {
                'model': self.model,
                'messages': [
                    {
                        'role': 'system',
                        'content': self.SYSTEM_PROMPT,
                    },
                    {'role': 'user', 'content': prompt},
                ],
                'temperature': self.temperature,
                'max_tokens': 2200,
            },
            headers={'Authorization': f'Bearer {api_key}'},
        )
        return data['choices'][0]['message']['content'].strip()

    def _call_ollama(self, prompt: str) -> str:
        host = _env_or_setting('OLLAMA_HOST', 'http://localhost:11434').rstrip('/')
        data = self._post_json(
            f'{host}/api/generate',
            {
                'model': self.model,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'temperature': self.temperature,
                    'num_predict': 2200,
                },
            },
        )
        return data.get('response', '').strip()

    @staticmethod
    def extract_python_code(response: str) -> str:
        """Extract the first Python code block from an LLM response."""
        if not response:
            return ''

        fenced_blocks = re.findall(r'```([^\n`]*)\n(.*?)```', response, flags=re.DOTALL)
        for language_tag, code in fenced_blocks:
            normalized_tag = language_tag.strip().lower()
            if not normalized_tag or normalized_tag.startswith(('python', 'py')):
                return code.strip()

        start = response.find('from manim import')
        if start >= 0:
            return response[start:].strip()

        return response.strip()

    @staticmethod
    def validate_scene_code(scene_code: str) -> str | None:
        """Return None for valid code, otherwise a short validation error."""
        if not scene_code.strip():
            return 'empty LLM response'

        compact_code = re.sub(r'\s+', '', scene_code)
        if 'construct(self)' not in compact_code:
            return 'scene code is missing construct(self)'

        try:
            compile(scene_code, '<llm-manim-scene>', 'exec')
        except SyntaxError as exc:
            return f'scene code does not compile: {exc}'

        if not LLMSceneGenerator.extract_scene_name(scene_code):
            return 'scene code has no scene class with construct(self)'

        return None

    @staticmethod
    def extract_scene_name(scene_code: str) -> str | None:
        """Return the first class with a construct(self) method."""
        try:
            tree = ast.parse(scene_code)
        except SyntaxError:
            return None

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if not isinstance(item, ast.FunctionDef) or item.name != 'construct':
                    continue
                if item.args.args and item.args.args[0].arg == 'self':
                    return node.name
        return None


class SceneGenerator:
    """Generate Manim scene code from math concepts.

    Strategy:
      1. Check for an exact template match
      2. Check for a domain match (partial template adaptation)
      3. Fall back to LLM generation (Phase 2)
    """

    def __init__(
        self,
        templates: dict[str, dict] | None = None,
        enable_llm: bool = True,
        scene_model: str | None = None,
        llm_generator: LLMSceneGenerator | None = None,
    ):
        self.templates = templates or SCENE_TEMPLATES
        self.enable_llm = enable_llm
        self.llm_generator = llm_generator
        self.scene_model = scene_model

    def _match_concept(self, concept: str) -> str | None:
        """Match a concept string to a known template key."""
        lowered = concept.lower().strip()

        # Exact match
        if lowered in self.templates:
            return lowered

        # Fuzzy match: check if concept words appear in template keys
        words = set(re.split(r'[\s\-_,]+', lowered))
        for key in self.templates:
            key_words = set(re.split(r'[\s\-_,]+', key))
            if words & key_words:
                return key

        return None

    def _match_domain(self, concept: str) -> str | None:
        """Match a concept to a mathematical domain."""
        lowered = concept.lower()
        for domain, keywords in CONCEPT_DOMAINS.items():
            if any(kw in lowered for kw in keywords):
                return domain
        return None

    def generate(self, concept: str, context: dict | None = None) -> GeneratedScene:
        """Generate a Manim scene for the given concept.

        Args:
            concept: Natural language description of the math concept.
            context: Optional session context (previous concepts, etc.)

        Returns:
            GeneratedScene with Manim Python code.
        """
        context = context or {}

        # Try template match
        template_key = self._match_concept(concept)
        if template_key:
            template = self.templates[template_key]
            return GeneratedScene(
                concept=concept,
                scene_name=template['name'],
                scene_code=template['template'].lstrip(),
                base_class=template.get('base_class', 'Scene'),
                description=template.get('description', ''),
                source='template',
                metadata={'template_key': template_key},
            )

        domain = self._match_domain(concept) or 'general'
        scene_name = _scene_name_from_concept(concept)

        if self.enable_llm:
            llm_generator = self.llm_generator or LLMSceneGenerator(model=self.scene_model)
            return llm_generator.generate(
                concept,
                context=context,
                scene_name=scene_name,
                domain=domain,
            )

        placeholder = self._generate_placeholder(concept, scene_name, domain)
        return GeneratedScene(
            concept=concept,
            scene_name=scene_name,
            scene_code=placeholder,
            base_class='Scene',
            description=f'Auto-generated scene for: {concept}',
            source='placeholder',
            metadata={'domain': domain},
        )

    def _generate_placeholder(self, concept: str, scene_name: str, domain: str) -> str:
        """Generate a placeholder Manim scene for concepts without templates.

        This creates a minimal working scene that can be refined later
        by LLM generation or manual editing.
        """
        return _build_placeholder_scene(concept, scene_name, domain)
