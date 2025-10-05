# accounts/urls.py

from .views import *
from rest_framework_simplejwt.views import TokenRefreshView
from django.urls import path
from .views import RegisterView



urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('login_page/',login_view,name='login_page'),
    path('signup_page/',signup_view,name='signup_page'),
]
