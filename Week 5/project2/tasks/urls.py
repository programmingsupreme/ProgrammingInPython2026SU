from django.urls import path

from . import views

urlpatterns = [
    path("", views.TaskListView.as_view(), name="task-list"),
    path("task/new/", views.TaskCreateView.as_view(), name="task-create"),
    path("task/<int:pk>/edit/", views.TaskUpdateView.as_view(), name="task-update"),
    path("task/<int:pk>/delete/", views.TaskDeleteView.as_view(), name="task-delete"),
    path("task/<int:pk>/toggle/", views.toggle_complete, name="task-toggle"),
    path("task/quick-add/", views.quick_add_task, name="task-quick-add"),
    path("calendar/", views.task_calendar, name="task-calendar"),
    path("lists/", views.task_lists, name="task-lists"),
    path("register/", views.register, name="register"),
    path("settings/", views.account_settings, name="account-settings"),
    path("settings/openai-key/remove/", views.remove_openai_key, name="account-openai-key-remove"),
    path("settings/gemini-key/", views.save_gemini_key, name="account-gemini-key"),
    path("settings/gemini-key/remove/", views.remove_gemini_key, name="account-gemini-key-remove"),
    path("settings/provider/", views.set_ai_provider, name="account-provider"),
    path("shop/", views.theme_shop, name="theme-shop"),
    path("shop/<str:theme_key>/select/", views.select_theme, name="theme-select"),
]
