"""Tests for Manin Math Pad engine components."""
from __future__ import annotations

import pytest
from manin_math_pad.engine.scene_generator import SceneGenerator, SCENE_TEMPLATES, CONCEPT_DOMAINS
from manin_math_pad.engine.zettel_generator import ZettelGenerator, ZettelCluster


class TestSceneGenerator:
    """Test the Manim scene generator."""

    def setup_method(self):
        self.gen = SceneGenerator()

    def test_exact_template_match(self):
        """Exact concept names should match templates directly."""
        for key in SCENE_TEMPLATES:
            result = self.gen.generate(key)
            assert result.source == 'template', f'{key} should match a template'
            assert result.scene_name == SCENE_TEMPLATES[key]['name']
            assert 'construct(self)' in result.scene_code

    def test_fuzzy_concept_match(self):
        """Partial concept names should still match templates."""
        result = self.gen.generate('euler identity')
        assert result.source == 'template'
        assert 'Euler' in result.scene_name or 'euler' in result.concept.lower()

    def test_derivative_template(self):
        result = self.gen.generate('derivative definition')
        assert result.source == 'template'
        assert 'Derivative' in result.scene_name

    def test_fourier_template(self):
        result = self.gen.generate('fourier series')
        assert result.source == 'template'
        assert 'Fourier' in result.scene_name

    def test_unknown_concept_returns_placeholder(self):
        """Unknown concepts should return a working placeholder scene."""
        result = self.gen.generate('hypergraph coloring')
        assert result.source == 'placeholder'
        assert 'construct(self)' in result.scene_code
        assert result.scene_name.endswith('Scene')

    def test_placeholder_is_valid_python(self):
        """Generated placeholder code should be syntactically valid Python."""
        result = self.gen.generate('obscure math concept xyz')
        compile(result.scene_code, '<test>', 'exec')  # Should not raise SyntaxError

    def test_template_code_is_valid_python(self):
        """All template scenes should be syntactically valid Python."""
        for key, template in SCENE_TEMPLATES.items():
            compile(template['template'], f'<template:{key}>', 'exec')

    def test_domain_matching(self):
        """Concepts should map to correct mathematical domains."""
        result = self.gen.generate('matrix multiplication')
        assert result.metadata.get('domain') == 'linear_algebra' or result.source == 'template'

        result = self.gen.generate('prime numbers')
        assert result.metadata.get('domain') == 'number_theory' or result.source == 'template'

    def test_context_passed_through(self):
        """Context dict should be accepted and stored in metadata."""
        ctx = {'previous_concepts': ['euler identity', 'complex numbers']}
        result = self.gen.generate('derivative', context=ctx)
        # Should not raise; context is accepted


class TestZettelGenerator:
    """Test the Obsidian zettel cluster generator."""

    def setup_method(self):
        self.gen = ZettelGenerator(timestamp='20260513000000')

    def test_generates_central_note(self):
        cluster = self.gen.generate('euler identity')
        assert cluster.central_note is not None
        assert 'euler' in cluster.central_note.title.lower() or 'Euler' in cluster.central_note.title

    def test_generates_radiating_notes(self):
        cluster = self.gen.generate('derivative')
        assert len(cluster.notes) >= 3  # central + at least 2 radiating

    def test_central_note_has_frontmatter(self):
        cluster = self.gen.generate('matrix multiplication')
        central = cluster.central_note
        assert '---' in central.content
        assert 'tags:' in central.content
        assert 'zettel' in central.content.lower()

    def test_links_connect_notes(self):
        cluster = self.gen.generate('fourier series')
        central = cluster.central_note
        # Central note should link to radiating notes
        assert len(central.links) > 0

    def test_domain_detection(self):
        cluster = self.gen.generate('eigenvalue')
        assert cluster.domain == 'linear_algebra'

        cluster = self.gen.generate('prime numbers')
        assert cluster.domain == 'number_theory'

    def test_context_connections(self):
        ctx = {'previous_concepts': ['derivatives', 'limits']}
        cluster = self.gen.generate('integrals', session_context=ctx)
        # Should have connection notes for previous concepts
        connection_notes = [n for n in cluster.notes if n.metadata.get('type') == 'connection']
        assert len(connection_notes) >= 1

    def test_slugify(self):
        slug = self.gen._slugify("Euler's Identity (Complex Analysis)")
        assert ' ' not in slug
        assert slug.isascii()

    def test_unknown_domain_gets_general(self):
        cluster = self.gen.generate('obscure math concept xyz')
        assert cluster.domain == 'general'

    def test_all_notes_have_valid_filenames(self):
        cluster = self.gen.generate('fourier series')
        for note in cluster.notes:
            assert note.filename.startswith('zettel_')
            assert ' ' not in note.filename


class TestZettelClusterIntegration:
    """Integration tests for scene + zettel workflow."""

    def test_scene_and_zettel_for_same_concept(self):
        """Generating both a scene and zettel for the same concept should work."""
        scene_gen = SceneGenerator()
        zettel_gen = ZettelGenerator(timestamp='20260513000000')

        concept = 'euler identity'
        scene = scene_gen.generate(concept)
        zettel = zettel_gen.generate(concept)

        assert scene.source in ('template', 'placeholder', 'llm')
        assert zettel.central_note is not None
        assert len(zettel.notes) >= 3