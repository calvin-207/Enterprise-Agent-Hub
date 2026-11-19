from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from automation.models import TaskDefinition, TaskSchedule
from automation.scheduling import CRON_FIELDS, validate_cron
from automation.services import TASK_TITLES


class TaskDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskDefinition
        fields = ("id", "title", "task_type", "description", "enabled", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_task_type(self, value):
        if value not in TASK_TITLES:
            raise serializers.ValidationError("只允许平台已实现的任务类型")
        return value


class TaskScheduleSerializer(serializers.ModelSerializer):
    definition_title = serializers.CharField(source="definition.title", read_only=True)
    last_run_at = serializers.DateTimeField(source="periodic_task.last_run_at", read_only=True)

    class Meta:
        model = TaskSchedule
        fields = (
            "id", "name", "definition", "definition_title", "environment", "minute", "hour",
            "day_of_week", "day_of_month", "month_of_year", "enabled",
            "last_run_at", "last_triggered_at", "created_at", "updated_at",
        )
        read_only_fields = ("id", "environment", "last_run_at", "last_triggered_at", "created_at", "updated_at")

    def validate(self, attrs):
        fields = {
            key: attrs.get(key, getattr(self.instance, key) if self.instance else None)
            for key in CRON_FIELDS
        }
        # All fields have model defaults but allow omit on create for convenience.
        fields = {key: value for key, value in fields.items() if value is not None}
        try:
            normalized = validate_cron(fields)
        except DjangoValidationError:
            raise serializers.ValidationError({"cron": "Cron 表达式不合法，请检查分、时、星期、日期和月份"})
        attrs.update(normalized)
        definition = attrs.get("definition", self.instance.definition if self.instance else None)
        if not definition:
            raise serializers.ValidationError({"definition": "请选择任务定义"})
        if attrs.get("enabled", self.instance.enabled if self.instance else False) and not definition.enabled:
            raise serializers.ValidationError({"definition": "该任务定义已停用，请先启用"})
        return attrs
