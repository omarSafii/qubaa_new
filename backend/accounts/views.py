from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import RegisterSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import MyTokenObtainPairSerializer
from rest_framework.permissions import IsAuthenticated
from halaqas.access import assigned_halaqas_for_user, role_for_user


class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"msg": "تم إنشاء المستخدم بنجاح"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        profile = getattr(user, 'profile', None)
        return Response({
            "id": user.id,
            "username": user.username,
            "role": profile.role if profile else "unknown"
        })


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    

def _safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return ""


def _post_login_redirect(user, request=None):
    role = role_for_user(user)
    next_url = _safe_next_url(request) if request else ""

    if role == "teacher":
        halaqas = list(assigned_halaqas_for_user(user))
        if len(halaqas) == 1:
            return reverse("halaqas:halaqa_detail", args=[halaqas[0].pk])
        return reverse("teacher_halaqas")

    if role == "supervisor":
        return next_url or reverse("halaqas:supervisor_dashboard")

    if role == "admin":
        return next_url or reverse("halaqas:master_admin_dashboard")

    return next_url or reverse("halaqas:supervisor_dashboard")


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_post_login_redirect(request.user, request))

    context = {"next": request.GET.get("next", "")}
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            context["error"] = "اسم المستخدم أو كلمة المرور غير صحيحة."
        elif not user.is_active:
            context["error"] = "هذا الحساب غير مفعل."
        else:
            login(request, user)
            return redirect(_post_login_redirect(user, request))

    return render(request, 'accounts/login_page.html', context)


def legacy_login_page_view(request):
    return redirect("login")


@login_required
def teacher_halaqas_view(request):
    if role_for_user(request.user) != "teacher":
        return redirect(_post_login_redirect(request.user, request))

    halaqas = list(assigned_halaqas_for_user(request.user))
    if len(halaqas) == 1:
        return redirect("halaqas:halaqa_detail", pk=halaqas[0].pk)
    if not halaqas:
        messages.warning(request, "لا توجد حلقات مسندة لهذا الحساب حالياً.")

    return render(request, "accounts/teacher_halaqas.html", {"halaqas": halaqas})


def signup_view(request):
    return render(request, 'accounts/signup_page.html')
