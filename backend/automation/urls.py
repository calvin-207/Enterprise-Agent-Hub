from django.urls import path

from automation.views import AutomationView
from automation.schedule_views import DefinitionView, ScheduleView

urlpatterns = [
    path("definitions/", DefinitionView.as_view(), name="automation-definitions"),
    path("definitions/<int:definition_id>/", DefinitionView.as_view(), name="automation-definition-detail"),
    path("schedules/", ScheduleView.as_view(), name="automation-schedules"),
    path("schedules/<int:schedule_id>/", ScheduleView.as_view(), name="automation-schedule-detail"),
    path("schedules/<int:schedule_id>/run/", ScheduleView.as_view(), name="automation-schedule-run"),
    path("executions/", AutomationView.as_view(), name="automation-executions"),
    path("executions/<int:execution_id>/", AutomationView.as_view(), name="automation-execution-detail"),
    path("executions/<int:execution_id>/retry/", AutomationView.as_view(), name="automation-execution-retry"),
]
