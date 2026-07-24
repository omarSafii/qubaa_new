# accounts/urls.py

from .views import *
from rest_framework_simplejwt.views import TokenRefreshView
from django.urls import path
from .views import RegisterView



urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('login_page/', legacy_login_page_view, name='login_page'),
    path('my-halaqas/', teacher_halaqas_view, name='teacher_halaqas'),
    path('signup_page/',signup_view,name='signup_page'),
]
