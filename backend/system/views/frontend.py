import logging

from django.shortcuts import render
from django.views.generic import TemplateView
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from utils.file_upload import ImageUpload
from utils.jsonResponse import SuccessResponse,DetailResponse,ErrorResponse
from system.seo_defaults import SEO_LANDING_DEFAULTS
from system.views.system_config import getSystemConfig

logger = logging.getLogger(__name__)


class SeoLandingPageView(TemplateView):
    """
    官网 SEO 落地页（根路径 /）

    将「系统配置」中可由后台编辑的文案注入模板：
    - 基础配置 → 系统标题（app_name）
    - 官网 SEO 分组 → 标题 / 摘要 / 关键词 / 版权 / 备案号

    分组不存在（未执行 init）或读取异常时，使用 system/seo_defaults.py 的兜底值。
    """

    template_name = "leeadmin/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        seo = {}
        app_name = "Enterprise Agent Hub"
        try:
            base = getSystemConfig(key="base") or {}
            app_name = base.get("systitle") or app_name
            seo = getSystemConfig(key="seo") or {}
        except Exception:
            logger.exception("读取官网 SEO 配置失败，使用默认文案")

        values = dict(SEO_LANDING_DEFAULTS)
        values.update({k: v for k, v in seo.items() if v})
        # ICP 备案号支持留空隐藏：配置项存在但值为空时不回退默认值
        if "icp" in seo:
            values["icp"] = seo.get("icp") or ""
        context.update(
            app_name=app_name,
            seo_title=values["title"],
            seo_description=values["description"],
            seo_keywords=values["keywords"],
            seo_copyright=values["copyright"],
            seo_icp=values["icp"],
        )
        return context


#后端图片上传
class SysImagesUploadView(APIView):
    '''
    post:
    【功能描述】图片上传功能API</br>
    【参数说明】无，需要登录携带token后才能调用</br>
    '''
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        result = ImageUpload(request,"file", "platform")
        if result['code'] == 200:
            return SuccessResponse(data=result['img'], msg=result['msg'])
        else:
            return ErrorResponse(msg=result['msg'])

#h5端页面
def h5web(request):
    return render(request,"h5/index.html")