"""Deterministic math conversation support for Manim Math Pad."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .scene_generator import CONCEPT_DOMAINS, SceneGenerator


@dataclass(frozen=True)
class ChatTurn:
    """A generated chat response and updated session context."""

    answer: str
    concept: str
    domain: str
    context: dict
    artifact_context: dict


@dataclass(frozen=True)
class ConceptAnswerProfile:
    """Reusable explanation plan for a common math concept."""

    essence: str
    mental_model: str
    formal_view: str
    example: str
    misconception: str
    animation_steps: tuple[str, ...]


class MathChatService:
    """Answer math prompts using cached explanations with LLM fallback."""

    CONCEPT_ALIASES: tuple[tuple[str, str], ...] = (
        ('euler', 'euler identity'),
        ('fourier', 'fourier series'),
        ('matrix multiplication', 'matrix multiplication'),
        ('matrix product', 'matrix multiplication'),
        ('multiply matrices', 'matrix multiplication'),
        ('derivative', 'derivative'),
        ('integral', 'integral'),
        ('limit', 'limit'),
        ('eigen', 'eigenvectors'),
        ('matrix', 'matrix multiplication'),
    )

    KNOWN_PROFILES = {
        'derivative': (
            ConceptAnswerProfile(
                essence=(
                    'A derivative measures the instantaneous rate at which one quantity '
                    'changes with respect to another.'
                ),
                mental_model=(
                    'Start with two nearby points on a graph. The slope between them is an '
                    'average rate of change; as the second point slides closer, that secant '
                    'line settles into the tangent direction at the first point.'
                ),
                formal_view=(
                    'The formal object is the limit of a difference quotient: compare '
                    'f(x+h) with f(x), divide by h, then ask what value this ratio approaches '
                    'as h goes to 0.'
                ),
                example=(
                    'If position is s(t)=t^2, the average velocity from t=3 to t=3+h is '
                    '6+h, so the instantaneous velocity at t=3 is 6.'
                ),
                misconception=(
                    'The derivative is not the height of the graph. It is the local slope, '
                    'so two functions can have the same value at a point but different derivatives.'
                ),
                animation_steps=(
                    'plot a curve and mark one base point',
                    'draw a secant line to a movable nearby point',
                    'shrink the horizontal gap h',
                    'freeze the limiting tangent and label the derivative',
                ),
            )
        ),
        'limit': (
            ConceptAnswerProfile(
                essence=(
                    'A limit describes the value an expression approaches as its input '
                    'moves toward a target.'
                ),
                mental_model=(
                    'Think of approaching a point from nearby values rather than standing '
                    'on the point itself. The limit asks what the surrounding behavior is '
                    'forcing the output to become.'
                ),
                formal_view=(
                    'The epsilon-delta definition turns that idea into a promise: every '
                    'desired output tolerance can be guaranteed by choosing inputs close '
                    'enough to the target.'
                ),
                example=(
                    'The expression (x^2-1)/(x-1) is undefined at x=1, but nearby it behaves '
                    'like x+1, so its limit as x approaches 1 is 2.'
                ),
                misconception=(
                    'A limit does not require the function to be defined at the target point. '
                    'It is about approach behavior.'
                ),
                animation_steps=(
                    'show points approaching from both sides',
                    'track the corresponding output values',
                    'tighten an output band around the proposed limit',
                    'show that close enough inputs stay inside the band',
                ),
            )
        ),
        'euler': (
            ConceptAnswerProfile(
                essence=(
                    'Euler identity says that complex exponentials encode rotation: '
                    'e^(i*pi) lands exactly at -1.'
                ),
                mental_model=(
                    'Multiplying by e^(it) moves a point around the unit circle by angle t. '
                    'When t reaches pi, the point has traveled halfway around the circle.'
                ),
                formal_view=(
                    'Euler formula e^(it)=cos(t)+i sin(t) separates the rotating point into '
                    'horizontal and vertical coordinates.'
                ),
                example=(
                    'At t=pi, cos(pi)=-1 and sin(pi)=0, so e^(i*pi)=-1+0i.'
                ),
                misconception=(
                    'The identity is not a numerical coincidence. It is the coordinate form '
                    'of rotation in the complex plane.'
                ),
                animation_steps=(
                    'draw the complex plane and unit circle',
                    'move a point from angle 0 to angle pi',
                    'show cosine and sine as coordinates',
                    'collapse the coordinates into -1',
                ),
            )
        ),
        'matrix': (
            ConceptAnswerProfile(
                essence=(
                    'Matrix multiplication is the rule for composing linear transformations '
                    'or combining rows with columns.'
                ),
                mental_model=(
                    'Read each entry of the product as a dot product: one row asks a question, '
                    'one column supplies data, and their paired products are summed.'
                ),
                formal_view=(
                    'For C=AB, the entry c_ij equals the sum over k of a_ik b_kj. '
                    'The shared inner dimension is the index being summed away.'
                ),
                example=(
                    'For [[1,2],[3,4]] times [[5,6],[7,8]], the top-left entry is '
                    '1*5 + 2*7 = 19.'
                ),
                misconception=(
                    'Matrix multiplication is not element-by-element multiplication, and '
                    'AB usually differs from BA.'
                ),
                animation_steps=(
                    'place matrix A, matrix B, and an empty result grid',
                    'highlight one row and one column',
                    'multiply matching entries and sum them',
                    'repeat the pattern for the other result entries',
                ),
            )
        ),
        'fourier': (
            ConceptAnswerProfile(
                essence=(
                    'A Fourier series represents a periodic signal as a sum of sine and '
                    'cosine waves.'
                ),
                mental_model=(
                    'Each wave is a simple rotating rhythm. Adding more rhythms lets the '
                    'sum imitate sharper and more complicated periodic shapes.'
                ),
                formal_view=(
                    'The coefficients measure how strongly the signal aligns with each '
                    'frequency; orthogonality keeps those frequency measurements separated.'
                ),
                example=(
                    'A square wave can be approximated by adding odd sine waves with '
                    'decreasing amplitudes: the more terms you add, the sharper the corners look.'
                ),
                misconception=(
                    'A Fourier series is not just curve fitting. It decomposes a function into '
                    'independent frequency components.'
                ),
                animation_steps=(
                    'show the target wave',
                    'add the first sine wave',
                    'add successive odd harmonics',
                    'compare the approximation to the target after each stage',
                ),
            )
        ),
        'eigen': (
            ConceptAnswerProfile(
                essence=(
                    'An eigenvector is a direction that a linear transformation preserves.'
                ),
                mental_model=(
                    'Most vectors rotate or shear to a new direction, but an eigenvector stays '
                    'on its original line while only stretching, shrinking, or flipping.'
                ),
                formal_view=(
                    'The equation Av=lambda v says that applying A to v produces a scalar '
                    'multiple of the same vector.'
                ),
                example=(
                    'For a diagonal matrix diag(2, 1/2), the x-axis direction is stretched '
                    'by 2 and the y-axis direction is shrunk by 1/2.'
                ),
                misconception=(
                    'Eigenvectors are not usually every vector. They are special directions '
                    'that reveal the structure of the transformation.'
                ),
                animation_steps=(
                    'show a grid and several test vectors',
                    'apply the transformation',
                    'contrast a rotating vector with a preserved direction',
                    'label the eigenvalue as the stretch factor',
                ),
            )
        ),
        'integral': (
            ConceptAnswerProfile(
                essence=(
                    'An integral accumulates many small contributions into a total quantity.'
                ),
                mental_model=(
                    'Approximate the total with rectangles, strips, or slices. As the slices '
                    'get thinner, the approximation approaches the accumulated area or total.'
                ),
                formal_view=(
                    'A definite integral is the limit of Riemann sums; an antiderivative is '
                    'a function whose derivative recovers the original rate.'
                ),
                example=(
                    'If velocity is v(t)=2t, then the distance from t=0 to t=3 is the area '
                    'under the curve, integral_0^3 2t dt = 9.'
                ),
                misconception=(
                    'An integral is not only area. Area is one interpretation of accumulation; '
                    'the same idea counts mass, distance, probability, and work.'
                ),
                animation_steps=(
                    'draw a curve and coarse rectangles',
                    'increase the number of slices',
                    'show the rectangles converging to the region',
                    'label the accumulated total',
                ),
            )
        ),
    }

    def __init__(
        self,
        scene_generator: SceneGenerator | None = None,
        enable_llm_chat: bool = True,
        chat_model: str | None = None,
    ):
        self.scene_generator = scene_generator or SceneGenerator(enable_llm=False)
        self._llm_chat_enabled = enable_llm_chat
        self._chat_model = chat_model
        self._llm_chat: object | None = None

    def _chat_llm(self):
        """Lazy-init the LLM for chat responses."""
        if self._llm_chat is None and self._llm_chat_enabled:
            from .scene_generator import LLMSceneGenerator
            self._llm_chat = LLMSceneGenerator(model=self._chat_model)
        return self._llm_chat

    def respond(self, message: str, context: dict | None = None) -> ChatTurn:
        """Create an answer and update reusable session context."""
        context = dict(context or {})
        concept = self._focus_concept(message)
        domain = self._match_domain(concept)
        previous_concepts = self._concept_history(context)
        answer = self._build_answer(
            message=message,
            concept=concept,
            domain=domain,
            previous_concepts=previous_concepts,
        )

        concepts = [*previous_concepts, concept][-20:]
        domains = [*context.get('domains', []), domain][-20:]

        updated_context = {
            **context,
            'current_concept': concept,
            'current_domain': domain,
            'last_user_message': message,
            'concepts': concepts,
            'previous_concepts': previous_concepts[-20:],
            'domains': domains,
            'turn_count': int(context.get('turn_count', 0)) + 1,
        }
        artifact_context = {
            **updated_context,
            'previous_concepts': previous_concepts[-10:],
        }

        return ChatTurn(
            answer=answer,
            concept=concept,
            domain=domain,
            context=updated_context,
            artifact_context=artifact_context,
        )

    def artifact_context(self, context: dict | None, topic: str) -> dict:
        """Build zettel/animation context for direct artifact endpoints."""
        context = dict(context or {})
        previous = [item for item in self._concept_history(context) if item != topic]
        return {
            **context,
            'current_concept': topic,
            'previous_concepts': previous[-10:],
        }

    def _focus_concept(self, message: str) -> str:
        """Reduce a natural-language prompt to a reusable concept label."""
        cleaned = message.strip()
        lowered = cleaned.lower()
        lowered = re.sub(
            r'\b(please|can you|could you|would you|explain|describe|teach me|'
            r'what is|what are|how does|how do|animate|visualize|show me|draw|'
            r'render|create|make|zettel|notes|cluster|obsidian|for|about)\b',
            ' ',
            lowered,
        )
        lowered = re.sub(r'[^a-z0-9+\-*/^().\s]', ' ', lowered)
        lowered = re.sub(r'\s+', ' ', lowered).strip(' .?!')
        for alias, canonical in self.CONCEPT_ALIASES:
            if alias in lowered:
                return canonical
        return lowered or cleaned.strip(' .?!') or 'math concept'

    def _match_domain(self, concept: str) -> str:
        lowered = concept.lower()
        for domain, keywords in CONCEPT_DOMAINS.items():
            if any(keyword in lowered for keyword in keywords):
                return domain
        return 'general'

    def _concept_history(self, context: dict) -> list[str]:
        raw_history = context.get('concepts') or context.get('previous_concepts') or []
        return [str(item).strip() for item in raw_history if str(item).strip()]

    def _build_answer(
        self,
        message: str,
        concept: str,
        domain: str,
        previous_concepts: list[str] | None = None,
    ) -> str:
        profile = self._known_profile(concept)
        has_template = self.scene_generator._match_concept(concept) is not None
        domain_label = domain.replace('_', ' ')

        if profile:
            parts = [
                f'{concept.title()}: {profile.essence}',
                f'Intuition: {profile.mental_model}',
                f'Formal handle: {profile.formal_view}',
                f'Concrete check: {profile.example}',
                f'Common trap: {profile.misconception}',
            ]
        else:
            # Try LLM for a better explanation
            llm_answer = self._try_llm_answer(message, concept, domain)
            if llm_answer:
                parts = [llm_answer]
            else:
                parts = [
                    f'{concept.title()} is a topic in {domain_label}. '
                    f'To understand it, clarify the objects involved, the operations or '
                    f'transformations acting on them, and the invariants or quantities being tracked.'
                ]

        if previous_concepts:
            recent = ', '.join(previous_concepts[-3:])
            parts.append(
                f'Connection to this session: compare it with {recent}. Ask what object, '
                f'operation, or invariant is being reused.'
            )

        template_sentence = (
            'I also have a built-in Manim template for this concept.'
            if has_template
            else 'I can still create a starter Manim scene for it and refine the code from there.'
        )
        steps = profile.animation_steps if profile else (
            'introduce the object',
            'show the operation',
            'mark the invariant',
            'state the conclusion',
        )
        animation_plan = '; '.join(steps)

        parts.append(
            f'For animation, I would break it into steps: {animation_plan}. '
            f'{template_sentence}'
        )
        return '\n\n'.join(parts)

    def _try_llm_answer(self, message: str, concept: str, domain: str) -> str:
        """Use the LLM for a concise math explanation, falling back gracefully."""
        llm = self._chat_llm()
        if llm is None:
            return ''
        try:
            prompt = (
                f'Give a concise but useful explanation of "{concept}" (domain: {domain}). '
                f'The user asked: "{message}". '
                f'Use 4 short paragraphs: intuition, formal handle, concrete example, '
                f'and common trap. Avoid markdown headings and avoid unsupported claims.'
            )
            response = llm._call_llm(prompt)
            # Clean it up
            response = re.sub(r'\*\*|__|###|##|#|```|`', '', response)
            response = re.sub(r'\n{3,}', '\n\n', response).strip()
            if len(response) < 20 or len(response) > 800:
                return ''
            return response
        except Exception:
            return ''

    def _known_profile(self, concept: str) -> ConceptAnswerProfile | None:
        lowered = concept.lower()
        for keyword, profile in self.KNOWN_PROFILES.items():
            if keyword in lowered:
                return profile
        return None
