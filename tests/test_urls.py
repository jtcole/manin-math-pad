"""URL configuration for tests."""
from django.urls import path, include

urlpatterns = [
    path('api/manim/', include('manim_math_pad.urls')),
]