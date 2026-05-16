from django.contrib import admin
from .models import Animation, AnimationStoryboard, Message, Session, ZettelCluster


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('uid', 'title', 'created_at', 'updated_at')
    search_fields = ('title',)
    readonly_fields = ('uid', 'created_at')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('uid', 'session', 'role', 'created_at')
    list_filter = ('role',)
    readonly_fields = ('uid', 'created_at')


@admin.register(Animation)
class AnimationAdmin(admin.ModelAdmin):
    list_display = (
        'uid',
        'concept',
        'storyboard',
        'clip_index',
        'status',
        'created_at',
        'completed_at',
    )
    list_filter = ('status',)
    readonly_fields = ('uid', 'created_at')


@admin.register(AnimationStoryboard)
class AnimationStoryboardAdmin(admin.ModelAdmin):
    list_display = ('uid', 'concept', 'status', 'created_at', 'completed_at')
    list_filter = ('status',)
    readonly_fields = ('uid', 'created_at')


@admin.register(ZettelCluster)
class ZettelClusterAdmin(admin.ModelAdmin):
    list_display = ('uid', 'topic', 'status', 'note_count', 'created_at')
    list_filter = ('status',)
    readonly_fields = ('uid', 'created_at')
