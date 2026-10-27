from django.contrib import admin
from django.urls import include, path

from planner.views import signup

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/signup/", signup, name="signup"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("support.urls")),
    path("", include("planner.urls")),
]

# Custom error pages (used when DEBUG is False).
handler400 = "support.views.errors.bad_request"
handler403 = "support.views.errors.permission_denied"
handler404 = "support.views.errors.page_not_found"
handler500 = "support.views.errors.server_error"
