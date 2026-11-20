# -*- coding: utf-8 -*-

"""
@Remark: websocket的路由文件
"""

from django.urls import re_path, path

from system.views.wsmessage import NotificationConsumer
from system.views.wsopslog import OpsLogTailConsumer

websocket_urlpatterns = [
    re_path(r"^ws/msg/$", NotificationConsumer.as_asgi()),
    path("ws/ops/logs/", OpsLogTailConsumer.as_asgi()),
]
