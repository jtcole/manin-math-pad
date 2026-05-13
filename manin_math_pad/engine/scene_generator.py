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

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


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
        title = Tex(r"e^{i\\pi} = -1", font_size=72)
        title.to_edge(UP)
        self.play(Write(title))
        self.wait(0.5)

        # Unit circle
        circle = Circle(radius=2, color=BLUE)
        axes = Axes(x_range=[-3, 3], y_range=[-3, 3], x_length=6, y_length=6)
        self.play(Create(axes), Create(circle))
        self.wait(0.5)

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
            lambda: Tex(
                f"({{2 * np.cos(angle_tracker.get_value()):.2f}}, {{2 * np.sin(angle_tracker.get_value()):.2f}})",
                font_size=36
            ).next_to(dot, UR, buff=0.2)
        )

        self.play(FadeIn(dot), FadeIn(label))
        self.play(angle_tracker.animate.set_value(PI), run_time=3)

        # Show e^(i*pi) = -1
        result = Tex(r"$e^{i\\pi} = \\cos(\\pi) + i\\sin(\\pi) = -1 + 0i = -1$", font_size=42)
        result.to_edge(DOWN)
        self.play(Write(result))
        self.wait(2)
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
        curve_label = Tex(r"f(x) = \\frac{1}{2}x^2 - x + 2", font_size=36).to_edge(UR)
        self.play(Create(curve), Write(curve_label))

        # Point on curve
        x_val = 3
        point = axes.c2p(x_val, 0.5 * x_val**2 - x_val + 2)
        dot = Dot(point, color=YELLOW)

        # Secant line (h shrinking)
        h_tracker = ValueTracker(3)
        secant = always_redraw(
            lambda: axes.get_secant_slope_curve(
                lambda x: 0.5 * x**2 - x + 2,
                x_val,
                dx=h_tracker.get_value(),
                color=RED,
                secant_line_length=4
            )
        )
        self.play(FadeIn(dot), Create(secant))
        self.wait(0.5)

        # Animate h → 0
        title = Tex(r"f'(x) = \\lim_{h \\to 0} \\frac{f(x+h) - f(x)}{h}", font_size=48)
        title.to_edge(UP)
        self.play(Write(title))

        self.play(h_tracker.animate.set_value(0.01), run_time=4)
        self.wait(2)
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
        # Define matrices
        A = Matrix([["1", "2"], ["3", "4"]]).set_color(BLUE)
        A_label = Tex("A", font_size=48).next_to(A, UP)

        times = Tex(r"\\times", font_size=48).next_to(A, RIGHT)

        B = Matrix([["5", "6"], ["7", "8"]]).set_color(GREEN)
        B_label = Tex("B", font_size=48).next_to(B, UP)
        B.next_to(times, RIGHT)

        equals = Tex(r"=", font_size=48)

        C = Matrix([["19", "22"], ["43", "50"]]).set_color(YELLOW)
        C_label = Tex("C = AB", font_size=48).next_to(C, UP)
        C.next_to(equals, RIGHT)
        equals.next_to(B, RIGHT)

        group = VGroup(A, A_label, times, B, B_label, equals, C, C_label)
        group.move_to(ORIGIN)

        self.play(Write(A), Write(A_label))
        self.play(Write(times))
        self.play(Write(B), Write(B_label))
        self.wait(1)
        self.play(Write(equals), Write(C), Write(C_label))
        self.wait(2)

        # Show computation step
        step = Tex(r"c_{11} = 1 \\times 5 + 2 \\times 7 = 19", font_size=36)
        step.to_edge(DOWN)
        self.play(Write(step))
        self.wait(2)
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
        title = Tex("Fourier Series: Square Wave Approximation", font_size=42)
        title.to_edge(UP)
        self.play(Write(title))

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
            lambda: Tex(
                f"n = {int(n_terms_tracker.get_value())} terms",
                font_size=36
            ).to_edge(DR)
        )

        self.play(Create(fourier_curve), Write(terms_label))
        self.play(n_terms_tracker.animate.set_value(20), run_time=8, rate_func=linear)
        self.wait(2)
''',
    },
}

# ─── Concept → domain mapping ────────────────────────────────────────────────

CONCEPT_DOMAINS: dict[str, list[str]] = {
    'calculus': ['derivative', 'integral', 'limit', 'series', 'taylor', 'fourier', 'differentiation', 'integration', 'continuity', 'epsilon'],
    'linear_algebra': ['matrix', 'vector', 'eigenvalue', 'eigenvector', 'determinant', 'linear transformation', 'basis', 'span', 'null space', 'rank'],
    'complex_analysis': ['euler', 'complex', 'imaginary', 'polar', 'conformal', 'residue', 'cauchy'],
    'topology': ['topology', 'manifold', 'homotopy', 'homology', 'knot', 'morse', 'borsuk'],
    'number_theory': ['prime', 'modular', 'congruence', 'fermat', 'riemann zeta', 'goldbach', 'twin prime'],
    'probability': ['probability', 'distribution', 'bayes', 'random', 'expectation', 'variance', 'markov', 'poisson', 'gaussian', 'central limit'],
    'geometry': ['circle', 'triangle', 'polygon', 'conic', 'ellipse', 'hyperbola', 'pythagorean', 'euclidean', 'non-euclidean'],
    'algebra': ['group', 'ring', 'field', 'isomorphism', 'homomorphism', 'abelian', 'galois', 'polynomial', 'abstract algebra'],
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
    source: str = 'template'  # 'template' or 'llm'
    metadata: dict = field(default_factory=dict)


class SceneGenerator:
    """Generate Manim scene code from math concepts.

    Strategy:
      1. Check for an exact template match
      2. Check for a domain match (partial template adaptation)
      3. Fall back to LLM generation (Phase 2)
    """

    def __init__(self, templates: dict[str, dict] | None = None):
        self.templates = templates or SCENE_TEMPLATES

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
                scene_code=template['template'],
                base_class=template.get('base_class', 'Scene'),
                description=template.get('description', ''),
                source='template',
                metadata={'template_key': template_key},
            )

        # No template match — for now, return a placeholder
        # Phase 2 will add LLM generation here
        domain = self._match_domain(concept) or 'general'
        scene_name = re.sub(r'[^a-zA-Z0-9]', '', concept.title())[:40] or 'CustomScene'

        if not scene_name.endswith('Scene'):
            scene_name += 'Scene'

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
        safe_concept = concept.replace('"', '\\"').replace("'", "\\'")
        return f'''
from manim import *

class {scene_name}(Scene):
    """
    Manim scene for: {safe_concept}
    Domain: {domain}

    This is a placeholder scene. Replace the construct() method
    with proper Manim animations for this concept.
    """
    def construct(self):
        title = Tex(r"{safe_concept}", font_size=48)
        title.to_edge(UP)
        self.play(Write(title))
        self.wait(1)

        # TODO: Add proper animation for {safe_concept}
        placeholder = Tex(r"(Animation placeholder)", font_size=36, color=GREY)
        placeholder.move_to(ORIGIN)
        self.play(FadeIn(placeholder))
        self.wait(2)
'''