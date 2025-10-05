from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import RegisterSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import MyTokenObtainPairSerializer
from rest_framework.permissions import IsAuthenticated


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
        return Response({
            "id": user.id,
            "username": user.username,
            "role": user.role  # افترضنا أنك خزنت الدور في حقل role
        })


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    
    
    
def login_view(request):
    return render(request, 'accounts/login_page.html')


def signup_view(request):
    return render(request, 'accounts/signup_page.html')
