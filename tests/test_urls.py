"""URL configuration for tests."""
from django.urls import path, include

urlpatterns = [
    path('api/manin/', include('manin_math_pad.urls')),
]