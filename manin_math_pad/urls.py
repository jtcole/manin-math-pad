"""
URL configuration for Manin Math Pad.

Routes:
  /api/manin/session/       — create/get chat session
  /api/manin/chat/           — send message, get response
  /api/manin/animate/        — generate Manim animation for a concept
  /api/manin/animate/<uid>/  — get animation status / download
  /api/manin/zettel/         — generate Obsidian zettel cluster
  /api/manin/zettel/<uid>/   — download zettel cluster
"""
from django.urls import path
from . import views

app_name = 'manin_math_pad'

urlpatterns = [
    path('session/', views.SessionView.as_view(), name='session'),
    path('chat/', views.ChatView.as_view(), name='chat'),
    path('animate/', views.AnimateView.as_view(), name='animate'),
    path('animate/<str:uid>/', views.AnimationStatusView.as_view(), name='animation_status'),
    path('zettel/', views.ZettelView.as_view(), name='zettel'),
    path('zettel/<str:uid>/', views.ZettelStatusView.as_view(), name='zettel_status'),
]