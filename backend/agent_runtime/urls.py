from django.urls import path
from agent_runtime.views import RunListAPI, RunDetailAPI, RunStepsAPI, RunEventsAPI, RunCancelAPI, RunUsageAPI

urlpatterns = [
    path("runs/", RunListAPI.as_view(), name="platform-runs"),
    path("runs/<uuid:run_id>/cancel/", RunCancelAPI.as_view(), name="platform-run-cancel"),
    path("runs/<uuid:run_id>/usage/", RunUsageAPI.as_view(), name="platform-run-usage"),
    path("runs/<uuid:run_id>/", RunDetailAPI.as_view(), name="platform-run-detail"),
    path("runs/<uuid:run_id>/steps/", RunStepsAPI.as_view(), name="platform-run-steps"),
    path("runs/<uuid:run_id>/events/", RunEventsAPI.as_view(), name="platform-run-events"),
]
