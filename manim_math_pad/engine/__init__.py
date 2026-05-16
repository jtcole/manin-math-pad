"""
Manim Math Pad — Core Engine.

The engine module handles:
  - scene_generator: LLM → Manim Python code generation
  - storyboard_generator: Concept → multiple connected Manim clip jobs
  - renderer: Manim scene rendering (Python subprocess)
  - zettel_generator: Concept → Obsidian zettel cluster generation
"""
