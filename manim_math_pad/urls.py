"""
URL configuration for Manim Math Pad.

Routes:
  /api/manim/session/       — create/get chat session
  /api/manim/session/<uid>/ — get session messages and artifacts
  /api/manim/session/<uid>/export/ — export transcript/code/artifacts zip
  /api/manim/chat/           — send message, get response
  /api/manim/chat/           — GET serves browser chat page
  /api/manim/animate/        — generate Manim animation for a concept
  /api/manim/animate/<uid>/  — get animation status / download
  /api/manim/storyboard/     — queue a multi-clip storyboard
  /api/manim/storyboard/<uid>/ — get/cancel storyboard status
  /api/manim/zettel/         — generate Obsidian zettel cluster
  /api/manim/zettel/<uid>/   — download zettel cluster
  /api/manim/zettel/<uid>/export/ — export one cluster to vault
  /api/manim/zettel/export-all/   — export all completed session clusters
"""
from django.urls import path
from . import views

app_name = 'manim_math_pad'

urlpatterns = [
    path('session/', views.SessionView.as_view(), name='session'),
    path('session/<str:uid>/export/', views.SessionExportView.as_view(), name='session_export'),
    path('session/<str:uid>/', views.SessionDetailView.as_view(), name='session_detail'),
    path('chat/', views.ChatView.as_view(), name='chat'),
    path('chat-ui/', views.ChatPageView.as_view(), name='chat_page'),
    path('animate/', views.AnimateView.as_view(), name='animate'),
    path('animate/<str:uid>/', views.AnimationStatusView.as_view(), name='animation_status'),
    path('storyboard/', views.StoryboardView.as_view(), name='storyboard'),
    path('storyboard/<str:uid>/', views.StoryboardStatusView.as_view(), name='storyboard_status'),
    path('zettel/', views.ZettelView.as_view(), name='zettel'),
    path('zettel/export-all/', views.ZettelExportAllView.as_view(), name='zettel_export_all'),
    path('zettel/<str:uid>/export/', views.ZettelExportView.as_view(), name='zettel_export'),
    path('zettel/<str:uid>/', views.ZettelStatusView.as_view(), name='zettel_status'),
]
