from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework.views import APIView

from automation.models import TaskExecution
from automation.serializers import TaskExecutionSerializer
from automation.services import TASK_TITLES, enqueue_execution


class IsAutomationAdministrator(permissions.BasePermission):
    """P0 restricts task creation/history to superusers, not regular staff."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active
                    and request.user.is_staff and request.user.is_superuser)


class AutomationView(APIView):
    def handle_exception(self, exc):
        # The legacy project exception handler wraps some authorization errors
        # as HTTP 200; this administrative API must preserve 401/403 semantics.
        if isinstance(exc, (AuthenticationFailed, NotAuthenticated, PermissionDenied)):
            response = exception_handler(exc, self.get_exception_handler_context())
            if response is not None:
                return response
        return super().handle_exception(exc)

    permission_classes = [permissions.IsAuthenticated, IsAutomationAdministrator]

    def get(self, request, execution_id=None):
        if execution_id is not None:
            execution = get_object_or_404(TaskExecution.objects.select_related("created_by"), pk=execution_id)
            return Response({"code": 2000, "msg": "success", "data": TaskExecutionSerializer(execution).data})

        try:
            page = max(1, int(request.query_params.get("page", "1")))
            limit = min(100, max(1, int(request.query_params.get("limit", "10"))))
        except (ValueError, TypeError):
            return Response({"code": 400, "msg": "分页参数无效"}, status=status.HTTP_400_BAD_REQUEST)
        state = request.query_params.get("status", "")
        if state and state not in TaskExecution.Status.values:
            return Response({"code": 400, "msg": "任务状态无效"}, status=status.HTTP_400_BAD_REQUEST)
        queryset = TaskExecution.objects.select_related("created_by").all()
        if state:
            queryset = queryset.filter(status=state)
        total = queryset.count()
        records = queryset[(page - 1) * limit:page * limit]
        counts = {value: 0 for value in TaskExecution.Status.values}
        for item in TaskExecution.objects.values("status").annotate(total=Count("id")):
            counts[item["status"]] = item["total"]
        return Response({
            "code": 2000, "msg": "success",
            "data": {"page": page, "limit": limit, "total": total,
                     "data": TaskExecutionSerializer(records, many=True).data,
                     "counts": counts},
        })

    def post(self, request, execution_id=None):
        if execution_id is None:
            task_type = request.data.get("task_type")
            if not isinstance(task_type, str) or task_type not in TASK_TITLES:
                return Response({"code": 400, "msg": "仅支持预定义检测任务"},
                                status=status.HTTP_400_BAD_REQUEST)
            execution = enqueue_execution(task_type=task_type, user=request.user)
            return Response({"code": 2000, "msg": "已提交任务", "data": TaskExecutionSerializer(execution).data},
                            status=status.HTTP_202_ACCEPTED)

        original = get_object_or_404(TaskExecution, pk=execution_id)
        if original.status != TaskExecution.Status.FAILED:
            return Response({"code": 400, "msg": "只有失败任务可以重新执行"},
                            status=status.HTTP_400_BAD_REQUEST)
        execution = enqueue_execution(task_type=original.task_type, user=request.user, retry_of=original)
        return Response({"code": 2000, "msg": "已提交重试任务", "data": TaskExecutionSerializer(execution).data},
                        status=status.HTTP_202_ACCEPTED)
