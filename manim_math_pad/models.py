"""
Manim Math Pad — Models.

Session: a chat session between a user and the math pad.
Message: individual messages within a session.
AnimationStoryboard: a multi-clip animation plan.
Animation: a Manim rendering job.
ZettelCluster: an Obsidian zettel cluster export job.
"""
from __future__ import annotations

import uuid
from django.db import models
from django.utils import timezone


class Session(models.Model):
    """A chat session with the Manim Math Pad."""
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    hidden_at = models.DateTimeField(null=True, blank=True)
    title = models.CharField(max_length=255, blank=True, default='')
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text='Session context: concepts discussed, current topic, etc.',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Session({self.uid}, "{self.title or "untitled"}")'


class Message(models.Model):
    """A single message in a chat session."""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Message({self.role}, session={self.session.uid})'


class AnimationStoryboard(models.Model):
    """A multi-step animation plan composed of renderable clips."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('rendering', 'Rendering clips'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('canceled', 'Canceled'),
    ]
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='storyboards')
    concept = models.CharField(max_length=255, help_text='Math concept being storyboarded')
    summary = models.TextField(blank=True, default='')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Storyboard metadata: domain, clip titles, generation source, etc.',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'AnimationStoryboard({self.concept}, {self.status})'


class Animation(models.Model):
    """A Manim animation rendering job."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('generating', 'Generating Manim scene'),
        ('rendering', 'Rendering video'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('canceled', 'Canceled'),
    ]
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='animations')
    storyboard = models.ForeignKey(
        AnimationStoryboard,
        on_delete=models.CASCADE,
        related_name='clips',
        null=True,
        blank=True,
    )
    concept = models.CharField(max_length=255, help_text='Math concept being animated')
    clip_index = models.PositiveIntegerField(null=True, blank=True)
    clip_count = models.PositiveIntegerField(null=True, blank=True)
    clip_title = models.CharField(max_length=255, blank=True, default='')
    clip_summary = models.TextField(blank=True, default='')
    scene_code = models.TextField(blank=True, default='', help_text='Generated Manim Python code')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    video_file = models.FileField(upload_to='manim/animations/', blank=True, null=True)
    thumbnail_file = models.FileField(upload_to='manim/thumbnails/', blank=True, null=True)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Rendering metadata: resolution, fps, etc.',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Animation({self.concept}, {self.status})'


class ZettelCluster(models.Model):
    """An Obsidian zettel cluster generation job."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('generating', 'Generating cluster'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='zettel_clusters')
    topic = models.CharField(max_length=255, help_text='Central topic for the zettel cluster')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    zettel_data = models.JSONField(
        default=dict,
        blank=True,
        help_text='Generated zettel cluster data',
    )
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    note_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'ZettelCluster({self.topic}, {self.status})'
