"""
Zettel Cluster Generator.

Generates Obsidian-compatible zettel clusters from math concepts.
Each cluster has a central note (the concept) and radiating notes
for related concepts, properties, theorems, examples, and connections.

Output format: Markdown files compatible with the cant_know vault structure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone


# ─── Zettel cluster templates by domain ──────────────────────────────────────

ZETTEL_TEMPLATES: dict[str, dict] = {
    'special_functions': {
        'central_fields': [
            'Definition',
            'Historical Problem',
            'Functional Equation',
            'Integral Model',
            'Applications',
        ],
        'link_types': ['extends', 'interpolates', 'satisfies', 'represents', 'applies_to'],
    },
    'calculus': {
        'central_fields': [
            'Definition',
            'Intuition',
            'Key Formula',
            'Common Mistakes',
            'Related Concepts',
        ],
        'link_types': ['generalizes', 'specializes', 'uses', 'proves', 'contrasts'],
    },
    'linear_algebra': {
        'central_fields': [
            'Definition',
            'Geometric Intuition',
            'Matrix Form',
            'Properties',
            'Applications',
        ],
        'link_types': ['generalizes', 'decomposes', 'transforms', 'dual', 'eigen'],
    },
    'complex_analysis': {
        'central_fields': [
            'Definition',
            'Geometric Interpretation',
            'Key Theorem',
            'Visualization',
            'Applications',
        ],
        'link_types': ['maps', 'preserves', 'conforms', 'extends', 'residue'],
    },
    'topology': {
        'central_fields': ['Definition', 'Intuition', 'Key Invariant', 'Examples', 'Theorems'],
        'link_types': ['homeomorphic', 'deforms', 'classifies', 'obstructs', 'fibrates'],
    },
    'number_theory': {
        'central_fields': ['Definition', 'Statement', 'Proof Sketch', 'Examples', 'Open Questions'],
        'link_types': ['implies', 'generalizes', 'conjectures', 'proves', 'extends'],
    },
    'probability': {
        'central_fields': [
            'Definition',
            'Intuition',
            'Formula',
            'Conditions',
            'Related Distributions',
        ],
        'link_types': ['generalizes', 'approximates', 'converges', 'conditions_on', 'marginalizes'],
    },
    'geometry': {
        'central_fields': [
            'Definition',
            'Construction',
            'Properties',
            'Theorems',
            'Real-world Examples',
        ],
        'link_types': ['generalizes', 'dual', 'projects', 'inscribes', 'tessellates'],
    },
    'algebra': {
        'central_fields': ['Definition', 'Axioms', 'Key Theorem', 'Examples', 'Classification'],
        'link_types': ['isomorphic', 'homomorphic', 'extends', 'quotient', 'subgroup'],
    },
}

DEFAULT_TEMPLATE = {
    'central_fields': ['Definition', 'Intuition', 'Key Results', 'Examples', 'Connections'],
    'link_types': ['related', 'generalizes', 'uses', 'proves', 'contrasts'],
}


@dataclass
class ZettelNote:
    """A single zettel note."""
    title: str
    filename: str
    content: str
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # wiki-links to other zettels
    metadata: dict = field(default_factory=dict)


@dataclass
class ZettelCluster:
    """A cluster of related zettel notes."""
    topic: str
    notes: list[ZettelNote] = field(default_factory=list)
    central_note: ZettelNote | None = None
    domain: str = 'general'


class ZettelGenerator:
    """Generate Obsidian zettel clusters from math concepts.

    Each cluster contains:
      1. A central note (the main concept)
      2. Radiating notes (properties, theorems, examples, connections)
      3. Wiki-links connecting all notes
      4. YAML frontmatter with metadata
    """

    def __init__(
        self,
        templates: dict[str, dict] | None = None,
        timestamp: str | None = None,
    ):
        self.templates = templates or ZETTEL_TEMPLATES
        self.timestamp = timestamp or datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')

    def _match_domain(self, concept: str) -> str:
        """Match a concept to a mathematical domain."""
        lowered = concept.lower()

        domain_keywords = {
            'calculus': [
                'derivative',
                'integral',
                'limit',
                'series',
                'taylor',
                'fourier',
                'differentiation',
                'epsilon',
                'continuity',
            ],
            'linear_algebra': [
                'matrix',
                'vector',
                'eigenvalue',
                'eigenvector',
                'determinant',
                'linear',
                'basis',
                'span',
                'rank',
            ],
            'complex_analysis': ['complex', 'imaginary', 'euler', 'polar', 'conformal', 'residue'],
            'topology': ['topology', 'manifold', 'homotopy', 'homology', 'knot', 'morse'],
            'number_theory': ['prime', 'modular', 'congruence', 'fermat', 'riemann', 'goldbach'],
            'probability': [
                'probability',
                'distribution',
                'bayes',
                'random',
                'expectation',
                'variance',
                'gaussian',
            ],
            'geometry': ['circle', 'triangle', 'polygon', 'conic', 'ellipse', 'pythagorean'],
            'algebra': ['group', 'ring', 'field', 'isomorphism', 'homomorphism', 'galois'],
            'special_functions': [
                'gamma function',
                'gamma',
                'factorial interpolation',
                'factorial',
                'euler integral',
                'beta function',
                'digamma',
            ],
        }

        for domain, keywords in domain_keywords.items():
            if any(kw in lowered for kw in keywords):
                return domain

        return 'general'

    def _slugify(self, text: str) -> str:
        """Convert text to a filename-safe slug."""
        slug = re.sub(r'[^\w\s-]', '', text.lower())
        slug = re.sub(r'[\s_]+', '-', slug.strip())
        return slug[:60]

    def generate(self, concept: str, session_context: dict | None = None) -> ZettelCluster:
        """Generate a zettel cluster for a math concept.

        Args:
            concept: The math concept to create a cluster for.
            session_context: Optional context from the chat session (previous concepts, etc.)

        Returns:
            ZettelCluster with central note and radiating notes.
        """
        session_context = session_context or {}
        domain = self._match_domain(concept)
        template = self.templates.get(domain, DEFAULT_TEMPLATE)
        lesson = self._lesson_from_context(session_context, concept)

        # Central note
        central = self._generate_central_note(concept, domain, template)
        if lesson:
            central.content = self._inject_lesson_contract(central.content, lesson)
            central.metadata['lesson_id'] = lesson.get('lesson_id')
        cluster = ZettelCluster(
            topic=concept,
            central_note=central,
            domain=domain,
        )
        cluster.notes.append(central)

        # Radiating notes
        for field_name in template['central_fields']:
            if field_name == 'Definition':
                continue  # Merged into central note
            note = self._generate_radiating_note(concept, field_name, domain, central.filename)
            cluster.notes.append(note)
            central.links.append(note.filename)

        storyline = self._generate_storyline_note(concept, domain, central.filename)
        cluster.notes.append(storyline)
        central.links.append(storyline.filename)

        if lesson:
            for note in self._generate_lesson_artifact_notes(lesson, domain, central.filename):
                cluster.notes.append(note)
                central.links.append(note.filename)

        # Context connections
        if session_context.get('previous_concepts'):
            for prev_concept in session_context['previous_concepts'][:3]:
                prev_slug = self._slugify(prev_concept)
                connection = ZettelNote(
                    title=f'{concept} connects to {prev_concept}',
                    filename=(
                        f'zettel_{self.timestamp}_'
                        f'{self._slugify(concept)}-connects-{prev_slug}'
                    ),
                    content=self._connection_content(concept, prev_concept, domain),
                    tags=[domain, 'connection', 'zettel'],
                    links=[central.filename, f'zettel_{prev_slug}'],
                    metadata={
                        'type': 'connection',
                        'concepts': [concept, prev_concept],
                        'domain': domain,
                    },
                )
                cluster.notes.append(connection)
                central.links.append(connection.filename)

        self._finalize_central_links(central)
        return cluster

    def _lesson_from_context(self, session_context: dict, concept: str) -> dict | None:
        """Extract a lesson artifact matching this concept from session context."""
        lesson = session_context.get('lesson') or session_context.get('lesson_artifact')
        if not isinstance(lesson, dict):
            return None
        lesson_concept = str(lesson.get('concept') or '').lower()
        if lesson_concept and lesson_concept not in concept.lower() and concept.lower() not in lesson_concept:
            return None
        return lesson

    def _inject_lesson_contract(self, content: str, lesson: dict) -> str:
        """Add the shared lesson contract to the central note."""
        plan = lesson.get('lesson_plan') or {}
        teaching = lesson.get('teaching_spec') or {}
        gates = lesson.get('quality_gates') or []
        gate_lines = '\n'.join(
            f'- {gate.get("name", "gate")}: {gate.get("check", "")}'
            for gate in gates
        ) or '- No quality gates recorded.'
        lesson_block = f"""
## Lesson Contract

- Lesson ID: `{lesson.get('lesson_id', '')}`
- Domain: {lesson.get('domain', 'general')}
- Target duration: {lesson.get('target_duration_seconds', 0)} seconds
- Visual model: {teaching.get('visual_metaphor', 'not recorded')}
- Learning goal: {plan.get('learning_goal', 'not recorded')}
- Worked example: {plan.get('example', 'not recorded')}
- Misconception guard: {plan.get('misconception', 'not recorded')}

### Publish Quality Gates

{gate_lines}

"""
        return content.replace('## Connections', lesson_block + '## Connections')

    def _generate_lesson_artifact_notes(
        self,
        lesson: dict,
        domain: str,
        central_filename: str,
    ) -> list[ZettelNote]:
        """Generate notes that preserve the lesson, media plan, and source paths."""
        concept = str(lesson.get('concept') or 'math concept')
        slug = self._slugify(concept)
        lesson_id = str(lesson.get('lesson_id') or '')
        teaching = lesson.get('teaching_spec') or {}
        plan = lesson.get('lesson_plan') or {}
        clips = lesson.get('clips') or []

        lesson_note = ZettelNote(
            title=f'{concept} - Lesson Plan',
            filename=f'zettel_{self.timestamp}_{slug}-lesson-plan',
            content=self._lesson_plan_note_content(lesson, central_filename),
            tags=[domain, 'lesson', 'zettel'],
            links=[central_filename],
            metadata={'type': 'lesson_plan', 'domain': domain, 'lesson_id': lesson_id},
        )
        media_note = ZettelNote(
            title=f'{concept} - Media And Source',
            filename=f'zettel_{self.timestamp}_{slug}-media-source',
            content=self._media_source_note_content(lesson, central_filename),
            tags=[domain, 'media', 'manim', 'zettel'],
            links=[central_filename],
            metadata={'type': 'media_source', 'domain': domain, 'lesson_id': lesson_id},
        )
        visual_note = ZettelNote(
            title=f'{concept} - Visual Model',
            filename=f'zettel_{self.timestamp}_{slug}-visual-model',
            content=f"""---
id: zettel_{self.timestamp}_{slug}-visual-model
created: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
modified: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
tags:
  - {domain}
  - visual-model
  - zettel
type: zettel
domain: {domain}
concept: "{concept}"
lesson_id: "{lesson_id}"
---

# {concept} - Visual Model

{teaching.get('visual_metaphor', self._core_insight_for(concept, domain))}

## Why This Model Works

{plan.get('learning_goal', self._core_insight_for(concept, domain))}

## What To Watch

{plan.get('misconception', self._misconception_for(concept, domain))}

## Clip Evidence

{self._clip_evidence_lines(clips)}

## Backlinks

- [[{central_filename}|{concept}]]
""",
            tags=[domain, 'visual-model', 'zettel'],
            links=[central_filename],
            metadata={'type': 'visual_model', 'domain': domain, 'lesson_id': lesson_id},
        )
        return [lesson_note, media_note, visual_note]

    def _lesson_plan_note_content(self, lesson: dict, central_filename: str) -> str:
        concept = str(lesson.get('concept') or 'math concept')
        slug = self._slugify(concept)
        domain = str(lesson.get('domain') or 'general')
        lesson_id = str(lesson.get('lesson_id') or '')
        plan = lesson.get('lesson_plan') or {}
        teaching = lesson.get('teaching_spec') or {}
        arc_lines = '\n'.join(
            f'{index}. {item}'
            for index, item in enumerate(teaching.get('narrative_arc') or [], start=1)
        ) or '1. Build a concrete example, then name the reusable idea.'
        clip_lines = '\n'.join(
            f'{clip.get("index")}. {clip.get("title")} - {clip.get("narration")}'
            for clip in lesson.get('clips') or []
        )
        return f"""---
id: zettel_{self.timestamp}_{slug}-lesson-plan
created: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
modified: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
tags:
  - {domain}
  - lesson
  - zettel
type: zettel
domain: {domain}
concept: "{concept}"
lesson_id: "{lesson_id}"
---

# {concept} - Lesson Plan

## Learner-Facing Summary

{lesson.get('summary', self._core_insight_for(concept, domain))}

## Learning Goal

{plan.get('learning_goal', '')}

## Narrative Arc

{arc_lines}

## Worked Example

{plan.get('example', self._example_for(concept, domain))}

## Misconception Guard

{plan.get('misconception', self._misconception_for(concept, domain))}

## Clip Plan

{clip_lines}

## Backlinks

- [[{central_filename}|{concept}]]
"""

    def _media_source_note_content(self, lesson: dict, central_filename: str) -> str:
        concept = str(lesson.get('concept') or 'math concept')
        slug = self._slugify(concept)
        domain = str(lesson.get('domain') or 'general')
        lesson_id = str(lesson.get('lesson_id') or '')
        contract = (lesson.get('teaching_spec') or {}).get('artifact_contract') or {}
        artifact_lines = '\n'.join(
            f'- {label}: `{path}`'
            for label, path in contract.items()
        ) or '- video.mp4, captions.vtt, and clips/*.py after render.'
        source_lines = '\n'.join(
            (
                f'- Clip {clip.get("index")}: `{clip.get("scene_name")}` '
                f'({clip.get("duration_seconds")}s)'
            )
            for clip in lesson.get('clips') or []
        )
        captions = '\n'.join(
            (
                f'- {subtitle.get("start_seconds")}s-{subtitle.get("end_seconds")}s: '
                f'{subtitle.get("text")}'
            )
            for subtitle in lesson.get('subtitles') or []
        )
        return f"""---
id: zettel_{self.timestamp}_{slug}-media-source
created: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
modified: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
tags:
  - {domain}
  - manim
  - media
  - zettel
type: zettel
domain: {domain}
concept: "{concept}"
lesson_id: "{lesson_id}"
---

# {concept} - Media And Source

This note keeps the reproducibility trail for the lesson video.

## Artifact Contract

{artifact_lines}

## Manim Scene Entrypoints

{source_lines}

## Captions

{captions}

## Recreate

Use `lesson.json` as the source of truth. Render the clips, assemble `video.mp4`,
and keep `captions.vtt` beside the final video so captions can be toggled.

## Backlinks

- [[{central_filename}|{concept}]]
"""

    def _clip_evidence_lines(self, clips: list[dict]) -> str:
        if not clips:
            return '- No clips recorded.'
        return '\n'.join(
            f'- Clip {clip.get("index")}: {clip.get("visual_action")}'
            for clip in clips
        )

    def _finalize_central_links(self, central: ZettelNote) -> None:
        """Render collected wiki-links into the central note."""
        if central.links:
            links = '\n'.join(f'- [[{link}]]' for link in central.links)
        else:
            links = '- No linked notes yet.'
        central.content = central.content.replace('{{links}}', links)

    def _field_content(self, concept: str, field_name: str, domain: str) -> str:
        """Return deterministic, populated note content for one cluster aspect."""
        concept_title = concept.title()
        domain_label = domain.replace('_', ' ')
        field_key = field_name.lower()
        example = self._example_for(concept, domain)
        checkpoints = self._checkpoints_for(concept, domain)
        if 'gamma' in concept.lower():
            return self._gamma_field_content(field_key, example, checkpoints)

        if 'definition' in field_key or 'statement' in field_key:
            core = (
                f'{concept_title} names a {domain_label} idea by fixing the objects, '
                f'the allowed operations, and the relation being studied. A useful '
                f'working definition should make clear what counts as an example, '
                f'what data is required, and which quantities are preserved.'
            )
        elif 'intuition' in field_key or 'geometric' in field_key or 'visualization' in field_key:
            core = (
                f'The intuition for {concept} is to track what changes and what remains '
                f'invariant as the representation moves. A good animation should make '
                f'the invariant visible first, then show the transformation or limiting '
                f'process that reveals the structure.'
            )
        elif 'formula' in field_key or 'matrix' in field_key or 'axiom' in field_key:
            core = (
                f'The symbolic form for {concept} should be read as a compact record of '
                f'assumptions and operations. Identify the inputs, the rule that combines '
                f'them, and the output being compared; this prevents the notation from '
                f'becoming detached from the mathematical action.'
            )
        elif 'mistake' in field_key or 'condition' in field_key:
            core = (
                f'A common failure mode is applying {concept} after one of its hypotheses '
                f'has been dropped. Check the domain, boundary cases, and whether the '
                f'objects involved satisfy the assumptions before transferring a result.'
            )
        elif 'application' in field_key or 'example' in field_key:
            core = (
                f'Use examples of {concept} that expose the mechanism, not just the final '
                f'answer. Start with a small concrete case, compute it directly, then '
                f'explain which part of the computation scales to the general situation.'
            )
        elif 'theorem' in field_key or 'result' in field_key or 'property' in field_key:
            core = (
                f'The important results around {concept} usually describe invariance, '
                f'existence, uniqueness, or approximation. State each result with its '
                f'conditions attached, then separate the proof idea from the formal proof.'
            )
        elif 'connection' in field_key or 'related' in field_key or 'classification' in field_key:
            core = (
                f'Place {concept} in a local map: what it generalizes, what it depends on, '
                f'and which neighboring ideas solve the same problem with different '
                f'constraints. These links are where the note becomes reusable.'
            )
        else:
            core = (
                f'This aspect of {concept} captures how the idea behaves inside {domain_label}. '
                f'Keep the note atomic: one claim, one example, and one link back to the '
                f'central concept.'
            )

        return (
            f'{core}\n\n'
            f'Working example: {example}\n\n'
            f'Checks: {checkpoints}'
        )

    def _gamma_field_content(self, field_key: str, example: str, checkpoints: str) -> str:
        """Return populated note content for the gamma-function lesson cluster."""
        if 'definition' in field_key:
            core = (
                'The gamma function extends the factorial pattern from isolated whole '
                'numbers to a continuous input. The modern positive-input model is an '
                'area under t^(x-1)e^(-t), and the crucial rule is Gamma(x+1)=x Gamma(x).'
            )
        elif 'historical' in field_key or 'intuition' in field_key:
            core = (
                'The original teaching problem is not "memorize a new special function." '
                'It is: factorial gives 0!, 1!, 2!, 3!, and 4!, but calculus asks what '
                'should happen at 2.5 or 1/2. The story begins with missing territory '
                'between integer islands.'
            )
        elif 'functional' in field_key or 'formula' in field_key:
            core = (
                'The recurrence is the engine: Gamma(x+1)=x Gamma(x). It preserves the '
                'factorial step n! = n(n-1)! while allowing x to slide continuously.'
            )
        elif 'integral' in field_key or 'visual' in field_key:
            core = (
                'Euler\'s integral turns the extension into an area machine. Changing x '
                'changes the shape of t^(x-1)e^(-t); measuring the area gives Gamma(x).'
            )
        elif 'application' in field_key or 'connection' in field_key:
            core = (
                'Gamma becomes reusable because the same extension appears in probability '
                'distributions, asymptotic estimates, beta integrals, and complex analysis.'
            )
        else:
            core = (
                'The note should keep one idea atomic: gamma is useful because it extends '
                'factorial while preserving a rule, not because it merely connects dots.'
            )
        return f'{core}\n\nWorking example: {example}\n\nChecks: {checkpoints}'

    def _example_for(self, concept: str, domain: str) -> str:
        lowered = concept.lower()
        if 'gamma' in lowered:
            return (
                'Gamma(5)=24 agrees with 4!, and Gamma(1/2)=sqrt(pi) shows that the '
                'same rule produces meaningful between-integer values.'
            )
        if 'derivative' in lowered:
            return 'For f(x)=x^2 at x=3, the secant slope is 6+h and the limiting slope is 6.'
        if 'limit' in lowered:
            return 'For (x^2-1)/(x-1), nearby values behave like x+1, so the limit at x=1 is 2.'
        if 'integral' in lowered:
            return 'For v(t)=2t on [0,3], the accumulated distance is the area under the curve, 9.'
        if 'euler' in lowered:
            return 'At angle pi on the unit circle, cos(pi)=-1 and sin(pi)=0, so e^(i*pi)=-1.'
        if 'matrix' in lowered:
            return 'The top-left entry of [[1,2],[3,4]][[5,6],[7,8]] is 1*5 + 2*7 = 19.'
        if 'fourier' in lowered:
            return 'A square wave becomes recognizable by adding the first odd sine terms, then sharper as more terms appear.'
        if 'eigen' in lowered:
            return 'Under diag(2, 1/2), the x-axis vector keeps its direction and doubles in length.'
        return (
            f'Choose the smallest concrete {domain.replace("_", " ")} example where the '
            f'definition can be computed by hand, then record what remains invariant.'
        )

    def _checkpoints_for(self, concept: str, domain: str) -> str:
        lowered = concept.lower()
        if 'gamma' in lowered:
            checks = [
                'identify the factorial dots already known',
                'state the recurrence Gamma(x+1)=x Gamma(x)',
                'explain why matching dots alone is not enough',
            ]
        elif any(word in lowered for word in ['derivative', 'limit', 'integral']):
            checks = [
                'identify the variable that is changing',
                'state the limiting or accumulating process',
                'test one boundary case',
            ]
        elif any(word in lowered for word in ['matrix', 'eigen', 'vector']):
            checks = [
                'name the objects and dimensions',
                'track what the transformation preserves',
                'compare a generic vector with a special case',
            ]
        elif any(word in lowered for word in ['euler', 'complex', 'fourier']):
            checks = [
                'separate coordinates or frequencies',
                'identify the invariant scale or period',
                'verify the special value with a small computation',
            ]
        else:
            checks = [
                f'name the {domain.replace("_", " ")} objects',
                'give a hand-checkable example',
                'state one condition where the idea does not apply',
            ]
        return '; '.join(checks) + '.'

    def _core_insight_for(self, concept: str, domain: str) -> str:
        lowered = concept.lower()
        if 'gamma' in lowered:
            return (
                'The gamma function solves the problem of extending factorial beyond whole '
                'numbers. The visual move is to replace isolated factorial dots with an '
                'area machine that still obeys the factorial step rule.'
            )
        if 'derivative' in lowered:
            return (
                'A derivative turns local change into a number. The key move is to replace '
                'a visible average slope with the limiting tangent slope at one point.'
            )
        if 'limit' in lowered:
            return (
                'A limit is about forced nearby behavior. The value at the target point can '
                'be missing or misleading; the surrounding values carry the claim.'
            )
        if 'integral' in lowered:
            return (
                'An integral turns many tiny contributions into one accumulated total. The '
                'same structure explains area, distance, mass, probability, and work.'
            )
        if 'euler' in lowered:
            return (
                'Euler formula is rotation written in coordinates. At t=pi, the rotating '
                'unit point reaches -1 on the real axis, which produces the identity.'
            )
        if 'matrix' in lowered:
            return (
                'Matrix multiplication is composition made computable. Each product entry '
                'asks how one output coordinate depends on a row-column pairing.'
            )
        if 'fourier' in lowered:
            return (
                'A Fourier series separates a periodic shape into independent frequencies. '
                'Adding terms reveals how simple waves can build sharp structure.'
            )
        if 'eigen' in lowered:
            return (
                'An eigenvector reveals a direction that survives a transformation. The '
                'eigenvalue records the stretch, shrink, or flip along that direction.'
            )
        return (
            f'The reusable insight is to name the {domain.replace("_", " ")} objects, '
            'track the operation applied to them, and identify what remains meaningful '
            'after the representation changes.'
        )

    def _misconception_for(self, concept: str, domain: str) -> str:
        lowered = concept.lower()
        if 'gamma' in lowered:
            return (
                'Do not treat gamma as just a smooth curve through factorial dots; the '
                'recurrence, integral representation, and regularity constraints carry the idea.'
            )
        if 'derivative' in lowered:
            return 'Do not confuse the derivative with graph height; it measures local slope.'
        if 'limit' in lowered:
            return 'Do not require the function to be defined at the target point.'
        if 'integral' in lowered:
            return (
                'Do not restrict integrals to geometric area when the same idea models '
                'accumulation.'
            )
        if 'euler' in lowered:
            return 'Do not treat e^(i*pi)+1=0 as numerology; it is a rotation statement.'
        if 'matrix' in lowered:
            return (
                'Do not multiply entries position-by-position unless the operation is '
                'explicitly Hadamard.'
            )
        if 'fourier' in lowered:
            return (
                'Do not read a Fourier series as arbitrary curve fitting; the frequencies '
                'are orthogonal components.'
            )
        if 'eigen' in lowered:
            return 'Do not expect every vector to be an eigenvector; most directions change.'
        return (
            f'Do not transfer a {domain.replace("_", " ")} result until the objects, '
            'assumptions, and boundary cases have been checked.'
        )

    def _learning_questions_for(self, concept: str) -> list[str]:
        lowered = concept.lower()
        if 'gamma' in lowered:
            return [
                'Which factorial values are already fixed before gamma is introduced?',
                'What does the recurrence Gamma(x+1)=x Gamma(x) preserve?',
                'How does Euler\'s integral turn a function value into an area?',
                'Why does an arbitrary smooth curve through the same dots fail as an explanation?',
            ]
        if 'derivative' in lowered:
            return [
                'What average rate is being refined into an instantaneous rate?',
                'Which point is fixed and which point is allowed to move?',
                'What does h represent before it goes to zero?',
                'How can the tangent slope be checked with a small polynomial example?',
            ]
        if 'matrix' in lowered:
            return [
                'What are the input and output dimensions?',
                'Which row and column produce each result entry?',
                'What transformation or composition is represented?',
                'Where would the calculation fail if the dimensions did not match?',
            ]
        if 'fourier' in lowered:
            return [
                'What periodic target is being approximated?',
                'Which frequencies are added first and why?',
                'How do the coefficients change the amplitude of each component?',
                'What feature improves as more terms are included?',
            ]
        return [
            f'What object does {concept} act on or describe?',
            'What operation, limit, transformation, or accumulation is happening?',
            'Which quantity stays meaningful while the representation changes?',
            'What is the smallest example that exposes the mechanism?',
        ]

    def _animation_beats_for(self, concept: str) -> list[str]:
        lowered = concept.lower()
        if 'gamma' in lowered:
            return [
                'plot factorial dots as isolated integer checkpoints',
                'draw the gamma curve and show the recurrence ladder',
                'switch to the Euler integral as a shaded area model',
                'check integer values and the half-step value Gamma(1/2)',
                'contrast with an arbitrary curve through the same dots',
            ]
        if 'derivative' in lowered:
            return [
                'plot the curve and choose a base point',
                'draw a secant line to a nearby moving point',
                'shrink h while displaying the difference quotient',
                'replace the secant with the tangent and label the derivative',
                'summarize rate of change in one sentence',
            ]
        if 'euler' in lowered:
            return [
                'draw the complex plane and unit circle',
                'start at 1 and label angle 0',
                'rotate the point through pi radians',
                'show cosine and sine coordinates updating',
                'substitute t=pi and conclude e^(i*pi)=-1',
            ]
        if 'matrix' in lowered:
            return [
                'show A, B, and an empty result matrix',
                'highlight one row and one column',
                'multiply paired entries and sum them',
                'write the result entry',
                'repeat the pattern for the remaining entries',
            ]
        if 'fourier' in lowered:
            return [
                'show the target square wave',
                'add the first sine term',
                'add the third and fifth harmonics',
                'increase the term count continuously',
                'compare the final approximation with the target',
            ]
        return [
            'introduce the object',
            'show the operation or transformation',
            'track the invariant or accumulated quantity',
            'work through one concrete example',
            'state the final takeaway',
        ]

    def _generate_central_note(self, concept: str, domain: str, template: dict) -> ZettelNote:
        """Generate the central (hub) note for the cluster."""
        slug = self._slugify(concept)
        filename = f'zettel_{self.timestamp}_{slug}'
        title = concept.title()

        fields_section = '\n'.join(
            f'### {field}\n\n{self._field_content(concept, field, domain)}\n'
            for field in template['central_fields']
        )
        learning_questions = '\n'.join(
            f'- {question}'
            for question in self._learning_questions_for(concept)
        )
        animation_beats = '\n'.join(
            f'{index}. {beat}'
            for index, beat in enumerate(self._animation_beats_for(concept), start=1)
        )

        content = f"""---
id: {filename}
created: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
modified: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
tags:
  - {domain}
  - zettel
  - math
type: zettel
domain: {domain}
concept: "{concept}"
---

# {title}

> _"The product of mathematical thinking is mathematical understanding, not theorems."_
> — Yuri Manin

## Overview

{concept} is a {domain.replace('_', ' ')} concept worth keeping as a reusable
thinking tool. This cluster separates the definition, intuition, examples, and
connections so the idea can support both conversation and animation work.

## Core Insight

{self._core_insight_for(concept, domain)}

## Learning Questions

{learning_questions}

## Working Example

{self._example_for(concept, domain)}

## Misconception To Guard Against

{self._misconception_for(concept, domain)}

{fields_section}

## Animations

- [[{filename}-animation|Manim Animation]] — visual demonstration

### Suggested Animation Beats

{animation_beats}

## Connections

{{{{links}}}}

## References

- Add a textbook, paper, or lecture note when this cluster is promoted from
  working notes to a permanent reference.
"""

        return ZettelNote(
            title=title,
            filename=filename,
            content=content,
            tags=[domain, 'zettel', 'math', 'central'],
            links=[],
            metadata={
                'type': 'central',
                'domain': domain,
                'concept': concept,
            },
        )

    def _generate_radiating_note(
        self, concept: str, field_name: str, domain: str, central_filename: str
    ) -> ZettelNote:
        """Generate a radiating (satellite) note connected to the central note."""
        slug = self._slugify(concept)
        field_slug = self._slugify(field_name)
        filename = f'zettel_{self.timestamp}_{slug}-{field_slug}'
        title = f'{concept} — {field_name}'
        aspect_content = self._field_content(concept, field_name, domain)

        content = f"""---
id: {filename}
created: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
modified: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
tags:
  - {domain}
  - zettel
  - {field_slug}
type: zettel
domain: {domain}
concept: "{concept}"
aspect: {field_name}
---

# {title}

{aspect_content}

## Atomic Claim

{field_name} is useful for {concept} when it can be checked against a concrete
example and then linked back to the central definition.

## Practice Check

Use the working example to test this note. If the example cannot show the claim,
the note is too vague and should be split or rewritten.

## Animation Cue

Show this aspect as one visible change on screen, then pause long enough to label
the object, operation, and invariant.

## Backlinks

- [[{central_filename}|{concept}]]

---

_Related to [[{central_filename}]]_
"""

        return ZettelNote(
            title=title,
            filename=filename,
            content=content,
            tags=[domain, 'zettel', field_slug],
            links=[central_filename],
            metadata={
                'type': 'radiating',
                'aspect': field_name,
                'domain': domain,
            },
        )

    def _generate_storyline_note(
        self,
        concept: str,
        domain: str,
        central_filename: str,
    ) -> ZettelNote:
        """Generate a storyline note that turns the cluster into a learning path."""
        slug = self._slugify(concept)
        filename = f'zettel_{self.timestamp}_{slug}-storyline'
        title = f'{concept} - Storyline'
        beat_sheet = '\n'.join(
            f'{index}. {beat}'
            for index, beat in enumerate(self._animation_beats_for(concept), start=1)
        )

        content = f"""---
id: {filename}
created: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
modified: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
tags:
  - {domain}
  - zettel
  - storyline
type: zettel
domain: {domain}
concept: "{concept}"
aspect: Storyline
---

# {title}

Start with the motivating question for {concept}. Introduce the smallest
example that makes the question concrete, then name the formal structure only
after the need for it is visible.

## Sequence

1. State the problem in plain language.
2. Show one concrete example or diagram.
3. Introduce the notation and the core invariant.
4. Work through the example one visible step at a time.
5. Pause on the conceptual turning point.
6. Connect the result to a neighboring concept or prior conversation.

## Animation Hook

The Manim scene should reveal the same sequence visually: object, operation,
invariant, and conclusion.

## Beat Sheet

{beat_sheet}

## Backlinks

- [[{central_filename}|{concept}]]
"""

        return ZettelNote(
            title=title,
            filename=filename,
            content=content,
            tags=[domain, 'zettel', 'storyline'],
            links=[central_filename],
            metadata={
                'type': 'storyline',
                'domain': domain,
            },
        )

    def _connection_content(self, concept_a: str, concept_b: str, domain: str) -> str:
        """Generate a connection note between two concepts."""
        slug_a = self._slugify(concept_a)
        slug_b = self._slugify(concept_b)
        filename = f'zettel_{self.timestamp}_{slug_a}-connects-{slug_b}'

        return f"""---
id: {filename}
created: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
modified: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
tags:
  - {domain}
  - connection
  - zettel
type: zettel
connection_type: concept_bridge
---

# {concept_a} connects to {concept_b}

This note records why {concept_a} and {concept_b} belong in the same local map.
Do not keep this bridge as a vague association: it should identify a reusable
operation, analogy, or constraint.

## {concept_a} to {concept_b}

Ask which structure in {concept_a} is reused by {concept_b}: a definition, a
calculation pattern, an invariant, or a limiting process.

## Transfer Example

Take the smallest example from {concept_a} and ask what must change before it
becomes an example of {concept_b}. The changed part reveals the real connection.

## {concept_b} to {concept_a}

Use {concept_b} as a check on {concept_a}. If the connection is real, an
example or counterexample from {concept_b} should clarify the scope of
{concept_a}.

## Shared Structure

Both notes should identify objects, transformations, and invariants. Keep this
bridge only if it helps move between the two concepts during problem solving or
explanation.

## Questions To Resolve

- What is preserved across both concepts?
- Which hypothesis appears in one concept but not the other?
- Can one concept generate a counterexample for the other?
"""
