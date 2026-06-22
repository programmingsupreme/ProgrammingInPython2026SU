from django.contrib import admin

from .models import Profile, Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "category", "complete", "completed_at", "created")
    list_filter = ("complete", "category", "user")
    search_fields = ("title", "description")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    # Never list the raw API key columns -- only whether one is set.
    list_display = ("user", "ai_provider", "has_openai", "has_gemini", "points", "active_theme")
    list_filter = ("ai_provider",)
    search_fields = ("user__username",)

    @admin.display(boolean=True, description="Has OpenAI key")
    def has_openai(self, obj):
        return obj.has_openai_key

    @admin.display(boolean=True, description="Has Gemini key")
    def has_gemini(self, obj):
        return obj.has_gemini_key
