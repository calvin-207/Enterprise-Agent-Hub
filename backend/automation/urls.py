from django.urls import path

from automation.views import AutomationView

urlpatterns = [
    path("executions/", AutomationView.as_view(), name="automation-executions"),
    path("executions/<int:execution_id>/", AutomationView.as_view(), name="automation-execution-detail"),
    path("executions/<int:execution_id>/retry/", AutomationView.as_view(), name="automation-execution-retry"),
]
