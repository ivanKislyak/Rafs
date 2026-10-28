from rest_framework import permissions

class IsReplyAuthorOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        pass

    def has_object_permission(self, request, view, obj):
        pass
