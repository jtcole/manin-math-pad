"""
URL configuration for Manim Math Pad.

Routes:
  /api/manim/session/       — create/get chat session
  /api/manim/session/<uid>/ — get session messages and artifacts
  /api/manim/chat/           — send message, get response
  /api/manim/chat/           — GET serves browser chat page
  /api/manim/animate/        — generate Manim animation for a concept
  /api/manim/animate/<uid>/  — get animation status / download
  /api/manim/zettel/         — generate Obsidian zettel cluster
  /api/manim/zettel/<uid>/   — download zettel cluster
"""
from django.urls import path
from . import views

app_name = 'manim_math_pad'

urlpatterns = [
    path('session/', views.SessionView.as_view(), name='session'),
    path('session/<str:uid>/', views.SessionDetailView.as_view(), name='session_detail'),
    path('chat/', views.ChatView.as_view(), name='chat'),
    path('chat-ui/', views.ChatPageView.as_view(), name='chat_page'),
    path('animate/', views.AnimateView.as_view(), name='animate'),
    path('animate/<str:uid>/', views.AnimationStatusView.as_view(), name='animation_status'),
    path('zettel/', views.ZettelView.as_view(), name='zettel'),
    path('zettel/<str:uid>/', views.ZettelStatusView.as_view(), name='zettel_status'),
]
