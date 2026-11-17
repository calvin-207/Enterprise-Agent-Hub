from rest_framework import serializers

from automation.models import TaskExecution


class TaskExecutionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = TaskExecution
        fields = (
            "id", "title", "task_type", "status", "celery_task_id",
            "created_by_name", "retry_of", "result", "error_message",
            "created_at", "started_at", "finished_at",
        )
        read_only_fields = fields
