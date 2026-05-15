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


class MathChatService:
    """Answer math prompts using cached explanations with LLM fallback."""

    KNOWN_EXPLANATIONS = {
        'derivative': (
            'A derivative measures local rate of change. Geometrically, it is the slope '
            'of the tangent line that a secant line approaches as the step size goes to zero.'
        ),
        'limit': (
            'A limit describes the value a quantity approaches as the input gets close to '
            'a target. The point is the approach behavior, not necessarily the value at the target.'
        ),
        'euler': (
            'Euler identity links exponential growth, rotation, and the unit circle: moving '
            'by pi radians in the complex plane lands at -1.'
        ),
        'matrix': (
            'Matrix multiplication composes linear actions. Each output entry records how '
            'one row of the first matrix combines with one column of the second.'
        ),
        'fourier': (
            'A Fourier series rebuilds a repeating signal from sine and cosine waves. More '
            'terms capture sharper features, while the coefficients record how much of each '
            'frequency is present.'
        ),
        'eigen': (
            'An eigenvector is a direction preserved by a linear transformation. The vector '
            'may stretch or shrink, but it does not rotate away from its original line.'
        ),
    }

    def __init__(self, scene_generator: SceneGenerator | None = None, enable_llm_chat: bool = True, chat_model: str | None = None):
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
        answer = self._build_answer(message=message, concept=concept, domain=domain)

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

    def _build_answer(self, message: str, concept: str, domain: str) -> str:
        snippet = self._known_explanation(concept)
        has_template = self.scene_generator._match_concept(concept) is not None
        domain_label = domain.replace('_', ' ')

        if snippet:
            lead = snippet
        else:
            # Try LLM for a better explanation
            llm_answer = self._try_llm_answer(message, concept, domain)
            if llm_answer:
                lead = llm_answer
            else:
                lead = (
                    f'{concept.title()} is a topic in {domain_label}. '
                    f'To understand it, clarify the objects involved, the operations or '
                    f'transformations acting on them, and the invariants or quantities being tracked.'
                )

        template_sentence = (
            'I also have a built-in Manim template for this concept.'
            if has_template
            else 'I can still create a starter Manim scene for it and refine the code from there.'
        )

        return (
            f'{lead}\n\n'
            f'In this conversation I would treat it as a {domain_label} topic. '
            f'The useful next step is to turn the idea into a small visual sequence: '
            f'first the object, then the operation, then the conclusion. {template_sentence}'
        )

    def _try_llm_answer(self, message: str, concept: str, domain: str) -> str:
        """Use the LLM for a concise math explanation, falling back gracefully."""
        llm = self._chat_llm()
        if llm is None:
            return ''
        try:
            prompt = (
                f'Give a 2-3 sentence explanation of "{concept}" (domain: {domain}). '
                f'The user asked: "{message}". '
                f'Be concise, accurate, and avoid markdown formatting. '
                f'Write in plain text suitable for a chat response.'
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

    def _known_explanation(self, concept: str) -> str:
        lowered = concept.lower()
        for keyword, explanation in self.KNOWN_EXPLANATIONS.items():
            if keyword in lowered:
                return explanation
        return ''
