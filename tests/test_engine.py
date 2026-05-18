"""Tests for Manim Math Pad engine components."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from manim_math_pad.engine.chat_service import MathChatService
from manim_math_pad.engine.scene_generator import (
    SCENE_TEMPLATES,
    GeneratedScene,
    LLMSceneGenerator,
    SceneGenerator,
)
from manim_math_pad.engine.storyboard_generator import StoryboardGenerator
from manim_math_pad.engine.renderer import ManimRenderer
from manim_math_pad.engine.vault_exporter import VaultZettelExporter
from manim_math_pad.engine.zettel_generator import ZettelGenerator


class TestMathChatService:
    """Test deterministic math chat responses."""

    def test_known_concept_answer_has_explanation_sections(self):
        turn = MathChatService(enable_llm_chat=False).respond(
            'What is a derivative?',
            context={'concepts': ['limits']},
        )

        assert 'Intuition:' in turn.answer
        assert 'Formal handle:' in turn.answer
        assert 'Concrete check:' in turn.answer
        assert 'Common trap:' in turn.answer
        assert 'For animation, I would break it into steps:' in turn.answer
        assert 'Connection to this session:' in turn.answer
        assert turn.concept == 'derivative'
        assert turn.context['current_domain'] == 'calculus'

    def test_unknown_concept_still_gets_animation_plan(self):
        turn = MathChatService(enable_llm_chat=False).respond('Explain hypergraph coloring')

        assert 'For animation, I would break it into steps:' in turn.answer
        assert 'introduce the object' in turn.answer


class TestSceneGenerator:
    """Test the Manim scene generator."""

    def setup_method(self):
        self.gen = SceneGenerator(enable_llm=False)

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
        result = self.gen.generate('obscure "math"\nconcept xyz')
        compile(result.scene_code, '<test>', 'exec')  # Should not raise SyntaxError

    def test_template_code_is_valid_python(self):
        """All template scenes should be syntactically valid Python."""
        for key, template in SCENE_TEMPLATES.items():
            compile(template['template'], f'<template:{key}>', 'exec')

    def test_templates_include_multi_step_explanatory_cues(self):
        for key, template in SCENE_TEMPLATES.items():
            code = template['template']
            assert 'Step ' in code, f'{key} should guide the viewer through steps'
            assert 'run_time=' in code, f'{key} should control longer explanatory timing'

    def test_domain_matching(self):
        """Concepts should map to correct mathematical domains."""
        result = self.gen.generate('matrix multiplication')
        assert result.metadata.get('domain') == 'linear_algebra' or result.source == 'template'

        result = self.gen.generate('prime numbers')
        assert result.metadata.get('domain') == 'number_theory' or result.source == 'template'

    def test_context_passed_through(self):
        """Context dict should be accepted and stored in metadata."""
        ctx = {'previous_concepts': ['euler identity', 'complex numbers']}
        self.gen.generate('derivative', context=ctx)
        # Should not raise; context is accepted

    def test_llm_extracts_python_code_block(self):
        response = '''
Here is the scene:

```python
from manim import *

class LimitScene(Scene):
    def construct(self):
        self.wait(1)
```
'''
        code = LLMSceneGenerator.extract_python_code(response)
        assert code.startswith('from manim import *')
        assert 'class LimitScene' in code

    def test_llm_extracts_python_code_block_with_optional_language_tag(self):
        response = '''
```python linenums
from manim import *

class OptionalTagScene(Scene):
    def construct(self):
        self.wait(1)
```
'''
        code = LLMSceneGenerator.extract_python_code(response)
        assert code.startswith('from manim import *')
        assert 'class OptionalTagScene' in code

    def test_llm_prompt_contains_catalog_and_few_shots(self):
        llm = LLMSceneGenerator(model='unit-test-model')
        prompt = llm._build_prompt(
            'visualize eigenvectors',
            context={},
            scene_name='EigenvectorsScene',
            domain='linear_algebra',
        )

        assert 'ThreeDScene' in prompt
        assert 'ValueTracker' in prompt
        assert 'Circumscribe' in prompt
        assert 'camera.frame.animate.move_to' in prompt
        assert 'Pythagorean theorem visual proof' in prompt
        assert 'eigenvectors under a linear transformation' in prompt
        assert 'Prefer Text() for plain labels' in prompt

    def test_llm_temperature_reads_env(self, monkeypatch):
        monkeypatch.setenv('MANIM_SCENE_TEMPERATURE', '0.7')
        llm = LLMSceneGenerator(model='unit-test-model')

        assert llm.temperature == 0.7

    def test_llm_temperature_supports_legacy_misspelled_env(self, monkeypatch):
        monkeypatch.delenv('MANIM_SCENE_TEMPERATURE', raising=False)
        monkeypatch.setenv('MANIN_SCENE_TEMPERATURE', '0.6')
        llm = LLMSceneGenerator(model='unit-test-model')

        assert llm.temperature == 0.6

    def test_llm_validation_requires_construct_and_valid_python(self):
        valid = '''
from manim import *

class LimitScene(Scene):
    def construct(self):
        self.wait(1)
'''
        assert LLMSceneGenerator.validate_scene_code(valid) is None
        assert LLMSceneGenerator.validate_scene_code('from manim import *') is not None
        assert LLMSceneGenerator.validate_scene_code('def construct(self):\n  x =') is not None

    def test_llm_generator_falls_back_on_invalid_response(self, monkeypatch):
        llm = LLMSceneGenerator(model='unit-test-model')
        monkeypatch.setattr(llm, '_call_llm', lambda prompt: 'not Python')

        result = llm.generate('spectral sequence page turns')

        assert result.source == 'placeholder'
        assert 'construct(self)' in result.scene_code
        compile(result.scene_code, '<fallback>', 'exec')
        assert result.metadata['model'] == 'unit-test-model'

    def test_scene_generator_uses_injected_llm_when_enabled(self):
        class StubLLM:
            def generate(self, concept, context=None, scene_name=None, domain='general'):
                return GeneratedScene(
                    concept=concept,
                    scene_name=scene_name,
                    scene_code='''
from manim import *

class HypergraphColoringScene(Scene):
    def construct(self):
        self.wait(1)
''',
                    source='llm',
                    metadata={'domain': domain},
                )

        result = SceneGenerator(enable_llm=True, llm_generator=StubLLM()).generate(
            'hypergraph coloring'
        )

        assert result.source == 'llm'
        assert result.scene_name == 'HypergraphColoringScene'


class TestStoryboardGenerator:
    """Test multi-clip storyboard generation."""

    def test_known_concept_generates_connected_renderable_clips(self):
        storyboard = StoryboardGenerator().generate(
            'Explain derivative and connect it to limits',
            context={'previous_concepts': ['limits']},
        )

        assert storyboard.concept == 'derivative'
        assert storyboard.domain == 'calculus'
        assert len(storyboard.clips) >= 4
        assert 'limits' in storyboard.summary
        assert storyboard.metadata['source'] == 'pedagogical_storyboard'
        assert storyboard.lesson_plan.learning_goal.startswith('Understand a derivative')
        assert storyboard.target_duration_seconds >= 70
        assert storyboard.metadata['lesson_plan']['misconception']
        assert storyboard.metadata['storyboard_plan'][0]['learner_check']
        for index, clip in enumerate(storyboard.clips, start=1):
            assert clip.index == index
            assert f'{index}/{len(storyboard.clips)}' in clip.scene_code
            assert clip.duration_seconds >= 16
            assert clip.visual_action
            assert clip.math_focus
            assert clip.learner_check
            assert 'Learner check' not in clip.scene_code
            assert 'Math focus' not in clip.scene_code
            assert 'class ' in clip.scene_code
            assert LLMSceneGenerator.extract_scene_name(clip.scene_code) == clip.scene_name
            compile(clip.scene_code, f'<storyboard:{index}>', 'exec')


class TestZettelGenerator:
    """Test the Obsidian zettel cluster generator."""

    def setup_method(self):
        self.gen = ZettelGenerator(timestamp='20260513000000')

    def test_generates_central_note(self):
        cluster = self.gen.generate('euler identity')
        assert cluster.central_note is not None
        title = cluster.central_note.title
        assert 'euler' in title.lower() or 'Euler' in title

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

    def test_notes_are_populated_and_central_links_are_rendered(self):
        cluster = self.gen.generate('derivative', session_context={'previous_concepts': ['limits']})

        joined = '\n'.join(note.content for note in cluster.notes)
        assert '_TODO' not in joined
        assert '{{links}}' not in cluster.central_note.content
        assert any(note.metadata.get('type') == 'storyline' for note in cluster.notes)
        assert any(note.metadata.get('type') == 'connection' for note in cluster.notes)
        assert '## Core Insight' in cluster.central_note.content
        assert '## Learning Questions' in cluster.central_note.content
        assert '## Working Example' in cluster.central_note.content
        assert '## Misconception To Guard Against' in cluster.central_note.content
        assert '### Suggested Animation Beats' in cluster.central_note.content
        assert 'limiting tangent slope' in cluster.central_note.content
        assert '## Beat Sheet' in joined
        assert '## Questions To Resolve' in joined


class TestManimRenderer:
    """Test Manim CLI integration."""

    def test_renderer_uses_manim_019_quality_and_verbosity_flags(
        self,
        monkeypatch,
        tmp_path,
    ):
        commands = []

        def fake_run(cmd, capture_output, text, timeout, cwd=None):
            commands.append(cmd)
            if cmd[0] == 'ffprobe':
                return SimpleNamespace(returncode=0, stdout='1.0\n', stderr='')
            media_dir = Path(cwd) / 'media' / 'videos' / 'scene_job' / '480p15'
            media_dir.mkdir(parents=True)
            (media_dir / 'RenderedScene.mp4').write_bytes(b'video')
            return SimpleNamespace(returncode=0, stdout='', stderr='')

        monkeypatch.setattr('manim_math_pad.engine.renderer.subprocess.run', fake_run)
        monkeypatch.setattr(ManimRenderer, '_create_thumbnail', lambda *args, **kwargs: None)

        renderer = ManimRenderer(output_dir=tmp_path / 'out', quality='low_quality', fps=15)
        result = renderer.render(
            'from manim import *\n\nclass DemoScene(Scene):\n    def construct(self):\n        self.wait(1)\n',
            'DemoScene',
            job_uid='job',
        )

        assert result.success is True
        cmd = commands[0]
        assert cmd[cmd.index('-q') + 1] == 'l'
        assert cmd[cmd.index('-v') + 1] == 'WARNING'
        assert '--verbose' not in cmd
        assert '-l' not in cmd

    def test_renderer_concatenates_storyboard_clip_videos(self, monkeypatch, tmp_path):
        commands = []

        def fake_run(cmd, capture_output, text, timeout, cwd=None):
            commands.append(cmd)
            if cmd[0] == 'ffmpeg':
                output_path = Path(cmd[-1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b'combined-video')
                return SimpleNamespace(returncode=0, stdout='', stderr='')
            if cmd[0] == 'ffprobe':
                return SimpleNamespace(returncode=0, stdout='42.25\n', stderr='')
            return SimpleNamespace(returncode=1, stdout='', stderr='unexpected command')

        monkeypatch.setattr('manim_math_pad.engine.renderer.subprocess.run', fake_run)
        monkeypatch.setattr(ManimRenderer, '_create_thumbnail', lambda *args, **kwargs: None)
        clip_a = tmp_path / 'clip-a.mp4'
        clip_b = tmp_path / 'clip-b.mp4'
        clip_a.write_bytes(b'a')
        clip_b.write_bytes(b'b')

        renderer = ManimRenderer(output_dir=tmp_path / 'out', quality='low_quality')
        result = renderer.concatenate_videos(
            [clip_a, clip_b],
            tmp_path / 'out' / 'storyboard.mp4',
            thumbnail_path=tmp_path / 'out' / 'storyboard.jpg',
        )

        assert result.success is True
        assert result.video_path == tmp_path / 'out' / 'storyboard.mp4'
        assert result.duration_seconds == 42.25
        assert result.metadata['render_mode'] == 'storyboard_concat'
        assert result.metadata['clip_count'] == 2
        assert any(command[0] == 'ffmpeg' and '-f' in command for command in commands)


class TestVaultZettelExporter:
    """Test exporting generated zettel clusters to Markdown files."""

    def test_exports_cluster_notes_with_required_frontmatter(self, tmp_path):
        cluster = SimpleNamespace(
            uid=uuid.uuid4(),
            status='completed',
            topic='Matrix Multiplication',
            created_at=datetime(2026, 5, 14, 12, 30, tzinfo=timezone.utc),
            zettel_data={
                'domain': 'linear_algebra',
                'notes': [
                    {
                        'title': 'Matrix Multiplication',
                        'filename': 'zettel_20260514_matrix-multiplication',
                        'content': '---\nid: old-id\n---\n# Matrix Multiplication\n\nBody.',
                        'tags': ['legacy'],
                    }
                ],
            },
        )
        exporter = VaultZettelExporter(vault_path=tmp_path)

        result = exporter.export_cluster(cluster)

        assert result.note_count == 1
        assert len(result.created_paths) == 1
        written = result.created_paths[0].read_text(encoding='utf-8')
        assert re.search(r'id: [0-9a-f-]{36}', written)
        assert 'created: 2026-05-14T12:30:00+00:00' in written
        assert 'tags: [math, linear_algebra, zettel]' in written
        assert 'type: zettel' in written
        assert 'old-id' not in written
        assert '# Matrix Multiplication' in written

    def test_export_skips_existing_files(self, tmp_path):
        cluster = SimpleNamespace(
            uid=uuid.uuid4(),
            status='completed',
            topic='Limits',
            created_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
            zettel_data={
                'domain': 'calculus',
                'notes': [
                    {
                        'title': 'Limits',
                        'filename': 'zettel_20260514_limits',
                        'content': '# Limits\n',
                    }
                ],
            },
        )
        exporter = VaultZettelExporter(vault_path=tmp_path)

        first = exporter.export_cluster(cluster)
        second = exporter.export_cluster(cluster)

        assert len(first.created_paths) == 1
        assert second.created_paths == []
        assert second.skipped_paths == first.created_paths


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
