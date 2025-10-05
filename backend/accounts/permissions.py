from rest_framework.permissions import BasePermission

class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.groups.filter(name='Teachers').exists()

class IsParent(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.groups.filter(name='Parents').exists()

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.groups.filter(name='Admins').exists()
