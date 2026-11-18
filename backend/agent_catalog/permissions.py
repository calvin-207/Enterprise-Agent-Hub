from rest_framework.permissions import BasePermission

from agent_catalog.services import is_platform_admin


class PlatformAgentAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_platform_admin(request.user)
