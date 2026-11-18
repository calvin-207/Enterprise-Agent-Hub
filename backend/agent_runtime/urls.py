from django.urls import path
from agent_runtime.session_views import SessionListAPI, SessionDetailAPI, SessionMessagesAPI, SessionRunAPI
from agent_runtime.stream_views import RunStreamAPI
from agent_runtime.views import RunListAPI, RunDetailAPI, RunStepsAPI, RunEventsAPI, RunCancelAPI, RunUsageAPI

urlpatterns = [
    path("sessions/", SessionListAPI.as_view(), name="platform-sessions"),
    path("sessions/<uuid:session_id>/", SessionDetailAPI.as_view(), name="platform-session-detail"),
    path("sessions/<uuid:session_id>/messages/", SessionMessagesAPI.as_view(), name="platform-session-messages"),
    path("sessions/<uuid:session_id>/runs/", SessionRunAPI.as_view(), name="platform-session-runs"),
    path("runs/<uuid:run_id>/stream/", RunStreamAPI.as_view(), name="platform-run-event-stream"),
    path("runs/", RunListAPI.as_view(), name="platform-runs"),
    path("runs/<uuid:run_id>/cancel/", RunCancelAPI.as_view(), name="platform-run-cancel"),
    path("runs/<uuid:run_id>/usage/", RunUsageAPI.as_view(), name="platform-run-usage"),
    path("runs/<uuid:run_id>/", RunDetailAPI.as_view(), name="platform-run-detail"),
    path("runs/<uuid:run_id>/steps/", RunStepsAPI.as_view(), name="platform-run-steps"),
    path("runs/<uuid:run_id>/events/", RunEventsAPI.as_view(), name="platform-run-events"),
]
