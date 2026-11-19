# -*- coding: utf-8 -*-

"""
@Remark: 自定义异常处理
"""

import logging
import traceback

from django.db.models import ProtectedError
from django.db.utils import DatabaseError
from rest_framework import exceptions
from rest_framework.exceptions import (
    APIException as DRFAPIException,
    AuthenticationFailed,
    NotAuthenticated,
    ValidationError,
    NotFound,
)
from rest_framework.views import set_rollback, exception_handler
from django.http.response import Http404

from utils.jsonResponse import ErrorResponse

logger = logging.getLogger(__name__)


def format_validation_errors(detail):
    """
    @Remark: 把 DRF 校验错误压平为可读文本，避免 ErrorDetail repr 泄漏到接口
    例: {'user': [ErrorDetail(string='无效主键 “2” － 对象不存在。', code='does_not_exist')]}
        -> "user: 无效主键 “2” － 对象不存在。"
    对普通字符串原样返回，可安全地用于任何 msg 场景。
    """
    def to_text(value):
        if isinstance(value, dict):
            parts = []
            for key, item in value.items():
                text = to_text(item)
                if not text:
                    continue
                # non_field_errors / detail 是整表错误，不再拼字段名
                if key in ("non_field_errors", "detail"):
                    parts.append(text)
                else:
                    parts.append("%s: %s" % (key, text))
            return "；".join(parts)
        if isinstance(value, (list, tuple)):
            return "；".join(t for t in (to_text(v) for v in value) if t)
        if value is None or value == "":
            return ""
        return str(value)

    return to_text(detail) or "请求参数错误"


def CustomExceptionHandler(ex, context):
    """
    统一异常拦截处理
    目的:(1)取消所有的500异常响应,统一响应为标准错误返回
        (2)准确显示错误信息
    :param ex:
    :param context:
    :return:
    """
    msg = ""
    code = 4000
    response = exception_handler(ex, context)
    if isinstance(ex, AuthenticationFailed):
        code = 4001
        if "User is inactive" in str(ex.detail):
            msg = "该账号已被禁用,请联系管理员"
        elif (
            response
            and response.data.get("detail")
            == "Given token not valid for any token type"
        ):
            msg = "身份认证已过期"
        else:
            msg = ex.detail
    elif isinstance(ex, NotAuthenticated):
        code = 4001
        msg = ex.detail
    elif isinstance(ex, exceptions.ValidationError):
        msg = format_validation_errors(ex.detail)
    elif "django.db.utils.IntegrityError" in str(type(ex)):
        msg = str(ex)
        res = msg.split(", ")
        if res[0] == "(1062":
            msg = "数据有重复，请检查后重试:%s" % msg
    elif isinstance(ex, Http404):
        code = 404
        msg = "404错误：您访问的地址不存在"
    elif isinstance(ex, DRFAPIException):
        set_rollback()
        msg = str(ex.detail)
    elif isinstance(ex, exceptions.APIException):
        set_rollback()
        msg = str(ex.detail)
    elif isinstance(ex, ProtectedError):
        set_rollback()
        msg = "删除失败:该条数据与其他数据有相关绑定"
    elif isinstance(ex, Exception):
        logger.error(traceback.format_exc())
        msg = str(ex)  # 原样输出错误

    return ErrorResponse(msg=msg, code=code)


class APIException(Exception):
    """
    通用异常:(1)用于接口请求是抛出移除, 此时code会被当做标准返回的code, message会被当做标准返回的msg
    """

    def __init__(self, code=201, message="API异常", args=("API异常",)):
        self.args = args
        self.code = code
        self.message = message

    def __str__(self):
        return self.message
