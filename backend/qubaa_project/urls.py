from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from accounts.views import CurrentUserView


def home_view(request):
    return HttpResponse("<h1>نظام حلقات القرآن - قيد التشغيل</h1>")


urlpatterns = [
    path("", home_view, name="home"),
    path("admin/", admin.site.urls),
    path("api-auth/", include("rest_framework.urls")),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/users/me/", CurrentUserView.as_view(), name="current-user"),
    path("accounts/", include("accounts.urls")),
    path("students/", include("students.urls")),
    path("halaqas/", include("halaqas.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
