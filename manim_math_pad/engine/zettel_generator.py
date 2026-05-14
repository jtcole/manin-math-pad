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

        # Central note
        central = self._generate_central_note(concept, domain, template)
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

        # Context connections
        if session_context.get('previous_concepts'):
            for prev_concept in session_context['previous_concepts'][:3]:
                prev_slug = self._slugify(prev_concept)
                connection = ZettelNote(
                    title=f'{concept} ↔ {prev_concept}',
                    filename=(
                        f'zettel_{self.timestamp}_'
                        f'{concept.lower().replace(" ", "-")}-connects-{prev_slug}'
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

        return cluster

    def _generate_central_note(self, concept: str, domain: str, template: dict) -> ZettelNote:
        """Generate the central (hub) note for the cluster."""
        slug = self._slugify(concept)
        filename = f'zettel_{self.timestamp}_{slug}'
        title = concept.title()

        fields_section = '\n'.join(
            f'### {field}\n\n_TODO: Add content_\n'
            for field in template['central_fields']
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

{concept} — a concept in {domain}.

{fields_section}

## Animations

- [[{filename}-animation|Manim Animation]] — visual demonstration

## Connections

{{{{links}}}}

## References

- _TODO: Add primary references_
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

_TODO: Add content for {field_name} of {concept}._

## Backlinks

- [[{central_filename}|← {concept}]]

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

# {concept_a} ↔ {concept_b}

_How do these concepts connect?_

## {concept_a} → {concept_b}

_TODO: Describe how {concept_a} leads to or informs {concept_b}._

## {concept_b} → {concept_a}

_TODO: Describe how {concept_b} relates back to {concept_a}._

## Shared Structure

_TODO: What structural similarities exist?_
"""
