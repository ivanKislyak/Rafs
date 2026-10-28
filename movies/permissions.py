from rest_framework import permissions

class IsReplyAuthorOrReadOnly(permissions.BasePermission):
    message = "Only the author can edit this reply"
    if request.method in permissions.SAFE_METHODS:
        return True

    def has_object_permission(self, request, view, obj):
        return request.user == obj.user
