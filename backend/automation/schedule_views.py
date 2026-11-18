"""Admin-only APIs for allowlisted task definitions and database-backed Cron plans."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from automation.models import TaskDefinition, TaskSchedule
from automation.schedule_serializers import TaskDefinitionSerializer, TaskScheduleSerializer
from automation.scheduling import delete_schedule, sync_schedule
from automation.services import enqueue_execution
from automation.views import AutomationView


def ok(data, message="success", http_status=status.HTTP_200_OK):
    return Response({"code": 2000, "msg": message, "data": data}, status=http_status)


def invalid(errors):
    return Response({"code": 400, "msg": "提交的数据无效", "errors": errors},
                    status=status.HTTP_400_BAD_REQUEST)


class DefinitionView(AutomationView):
    """The inherited AutomationView requires an active staff superuser."""

    def get(self, request, definition_id=None):
        if definition_id is not None:
            obj = get_object_or_404(TaskDefinition, pk=definition_id)
            return ok(TaskDefinitionSerializer(obj).data)
        return ok(TaskDefinitionSerializer(TaskDefinition.objects.all(), many=True).data)

    def post(self, request, definition_id=None):
        if definition_id is not None:
            return invalid({"detail": "操作不支持"})
        serializer = TaskDefinitionSerializer(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer.errors)
        obj = serializer.save(created_by=request.user)
        return ok(TaskDefinitionSerializer(obj).data, "任务定义已创建", status.HTTP_201_CREATED)

    def patch(self, request, definition_id=None):
        obj = get_object_or_404(TaskDefinition, pk=definition_id)
        serializer = TaskDefinitionSerializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return invalid(serializer.errors)
        with transaction.atomic():
            obj = serializer.save()
            # A disabled definition stops ALL its Beat schedules.
            for plan in obj.schedules.select_related("definition", "periodic_task"):
                sync_schedule(plan)
        return ok(TaskDefinitionSerializer(obj).data, "任务定义已更新")

    def delete(self, request, definition_id=None):
        obj = get_object_or_404(TaskDefinition, pk=definition_id)
        with transaction.atomic():
            for plan in list(obj.schedules.all()):
                delete_schedule(plan)
            obj.delete()  # Execution history remains with nullable FK
        return ok(None, "任务定义已删除")


class ScheduleView(AutomationView):
    def get(self, request, schedule_id=None):
        queryset = TaskSchedule.objects.select_related("definition", "periodic_task")
        if schedule_id is not None:
            return ok(TaskScheduleSerializer(get_object_or_404(queryset, pk=schedule_id)).data)
        return ok(TaskScheduleSerializer(queryset, many=True).data)

    def post(self, request, schedule_id=None):
        if schedule_id is not None:
            # Manual execution is only valid on the explicit /run/ endpoint.
            if request.resolver_match.url_name != "automation-schedule-run":
                return Response({"code": 405, "msg": "请使用 /run/ 触发任务"},
                                status=status.HTTP_405_METHOD_NOT_ALLOWED)
            # Explicit manual run: no arbitrary Celery task names.
            plan = get_object_or_404(
                TaskSchedule.objects.select_related("definition"), pk=schedule_id
            )
            if not plan.definition.enabled:
                return invalid({"definition": "任务定义已停用"})
            execution = enqueue_execution(
                task_type=plan.definition.task_type, user=request.user,
                definition=plan.definition, schedule=plan,
            )
            from automation.serializers import TaskExecutionSerializer
            return ok(TaskExecutionSerializer(execution).data, "计划已手动触发",
                      status.HTTP_202_ACCEPTED)

        serializer = TaskScheduleSerializer(data=request.data)
        if not serializer.is_valid():
            return invalid(serializer.errors)
        with transaction.atomic():
            obj = serializer.save(created_by=request.user)
            sync_schedule(obj)
        return ok(TaskScheduleSerializer(obj).data, "计划已创建", status.HTTP_201_CREATED)

    def patch(self, request, schedule_id=None):
        obj = get_object_or_404(TaskSchedule, pk=schedule_id)
        serializer = TaskScheduleSerializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return invalid(serializer.errors)
        with transaction.atomic():
            obj = serializer.save()
            sync_schedule(obj)
        return ok(TaskScheduleSerializer(obj).data, "计划已更新")

    def delete(self, request, schedule_id=None):
        obj = get_object_or_404(TaskSchedule, pk=schedule_id)
        delete_schedule(obj)
        return ok(None, "计划已删除")
