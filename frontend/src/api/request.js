import axios from "axios";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  getToken,
  autoStorage,
  getRereshToken,
  setToken,
  setRefreshToken,
} from "@/utils/util";
import sysConfig from "@/config";
import { cancelRequestState } from "@/store/cancelRequest";

let API_BASE_URL = sysConfig.API_URL;

var request = axios.create({
  timeout: sysConfig.TIMEOUT,
  retry: 3, // 重试次数
  retryDelay: 1000, // 重试间隔
});

request.interceptors.request.use((config) => {
  const cancelRequest = cancelRequestState();
  config.cancelToken = new axios.CancelToken((cancel) => {
    cancelRequest.addCancelToken(cancel);
  });
  return config;
});

// Single-flight refresh. Every waiting request receives the same resolution
// or rejection; a failed refresh must never leave a Promise pending forever.
let refreshPromise = null;
let loggingOut = false;

function handleLogout() {
  // Parallel 401s (e.g. page-mount Promise.all) share one refresh failure;
  // only surface the logout toast/redirect once.
  if (loggingOut) return;
  loggingOut = true;
  autoStorage.clear();
  ElMessage.error("登录信息失效，请重新登录");
  window.location.href = "/";
}

function isRefreshCall(config) {
  return typeof config?.url === "string" && config.url.includes("/api/token/refresh/");
}

// Both auth-failure dialects converge here: wrapped bodies with code 4001/401
// (HTTP 200, system endpoints) AND SimpleJWT's native HTTP 401 (platform
// endpoints like /api/platform/v1/*). Refresh once, retry once, else logout.
async function retryWithRefresh(original) {
  if (!original || original._authRetried || isRefreshCall(original)) {
    handleLogout();
    throw new Error("Authentication expired after retry");
  }
  original._authRetried = true;
  const accessToken = await refreshAccessToken();
  original.headers.Authorization = sysConfig.TOKEN_PREFIX + accessToken;
  return request(original);
}

function refreshAccessToken() {
  if (!refreshPromise) {
    const refreshToken = getRereshToken();
    if (!refreshToken) return Promise.reject(new Error("No refresh token"));
    refreshPromise = axios
      .post(API_BASE_URL + "/api/token/refresh/", { refresh: refreshToken })
      .then(({ data }) => {
        const payload = data?.data?.access ? data.data : data;
        if (!payload?.access || !payload?.refresh) {
          throw new Error("Token refresh response is invalid");
        }
        setToken("logintoken", payload.access);
        setRefreshToken("refreshtoken", payload.refresh);
        return payload.access;
      })
      .finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

request.interceptors.response.use(
  async (response) => {
    const authExpired =
      response.data?.code === 4001 || response.data?.code === 401 || response.status === 401;
    if (!authExpired) {
      return response;
    }
    try {
      return await retryWithRefresh(response.config);
    } catch (error) {
      handleLogout();
      return Promise.reject(error);
    }
  },
  (error) => {
    if (axios.isCancel(error)) {
      return Promise.reject(error);
    }
    // Native HTTP 401 (SimpleJWT "token_not_valid"): refresh + retry once
    // exactly like the wrapped business-code dialect above.
    if (error.response?.status === 401) {
      return retryWithRefresh(error.config).catch((refreshError) => {
        handleLogout();
        return Promise.reject(refreshError);
      });
    }
    if (error.response?.status === 404 && import.meta.env.PROD) {
      window.location.href = "/404";
    }
    const message = resolveErrorMessage(error);
    // 统一在拦截层提示一次，并改写 error.message 供页面 catch 使用；
    // handled 标记告诉页面无需再次弹窗
    error.message = message;
    error.handled = true;
    ElMessage.error(message);
    return Promise.reject(error);
  },
);

// HTTP 状态码兜底文案（后端未返回 msg 时使用）
const STATUS_MESSAGES = {
  400: "请求参数错误",
  401: "登录状态已失效，请重新登录",
  403: "没有权限执行此操作",
  404: "请求的资源不存在",
  405: "请求方式不被支持",
  409: "数据冲突，请刷新后重试",
  500: "服务器内部错误",
  502: "网关错误，请稍后重试",
  503: "服务暂不可用，请稍后重试",
  504: "网关超时，请稍后重试",
};

function resolveErrorMessage(error) {
  const data = error.response?.data;
  // 后端标准响应 {code, msg}，优先展示后端给出的具体原因
  if (data && typeof data === "object" && typeof data.msg === "string" && data.msg) {
    return data.msg;
  }
  if (error.code === "ECONNABORTED" || error.message?.includes("timeout")) {
    return "网络超时";
  }
  if (error.message === "Network Error") {
    return "网络连接错误";
  }
  if (error.response) {
    return STATUS_MESSAGES[error.response.status] || error.response.statusText || "请求失败";
  }
  return "网络请求失败";
}

function ajax(opt, method) {
  var token = getToken();
  // var timestamp=new Date().getTime();
  var params;

  if (opt.params) {
    //对传入的参数进行深拷贝，防止传入的参数对象被页面上其他逻辑改变，导致签名错误
    if (Object.prototype.toString.call(opt.params) != "[object FormData]") {
      // 不是formdata类型
      params = JSON.parse(JSON.stringify(opt.params));
    } else {
      //formdata类型
      params = opt.params;
    }
    if (method == "GET") {
      params = {
        ...params,
        // 't':timestamp
      };
    }
  } else {
    params = {};
  }

  if (method == "PUT" || method == "DELETE") {
    var config = {
      url: API_BASE_URL + opt.url + params.id + "/",
      method: method,
      headers: {
        Authorization: sysConfig.TOKEN_PREFIX + token,
      },
    };
    if (!params.id) {
      config = {
        url: API_BASE_URL + opt.url,
        method: method,
        headers: {
          Authorization: sysConfig.TOKEN_PREFIX + token,
        },
      };
    }

    method === "PUT" && (config.params = params);
    return new Promise((resolve, reject) => {
      request({
        url: config.url,
        method: method,
        headers: {
          Authorization: sysConfig.TOKEN_PREFIX + token,
        },
        data: params,
      })
        .then((res) => {
          resolve(res.data);
        })
        .catch((res) => {
          reject(res);
        });
    });
  } else if (method == "GET2") {
    var config2 = {
      url: API_BASE_URL + opt.url + params.id + "/",
      method: "GET",
      headers: {
        Authorization: sysConfig.TOKEN_PREFIX + token,
      },
    };
    if (!params.id) {
      config2 = {
        url: API_BASE_URL + opt.url,
        method: "GET",
        headers: {
          Authorization: sysConfig.TOKEN_PREFIX + token,
        },
      };
    }
    return new Promise((resolve, reject) => {
      // console.log(config,'config')
      request({
        url: config2.url,
        method: "GET",
        headers: {
          Authorization: sysConfig.TOKEN_PREFIX + token,
        },
        data: params,
      })
        .then((res) => {
          resolve(res.data);
        })
        .catch((res) => {
          reject(res);
        });
    });
  } else if (method == "excel") {
    let baseurl = API_BASE_URL + opt.url;
    var config3 = {
      url: buildUrlQuery(baseurl, opt.queryParams),
      method: "POST",
      headers: {
        Authorization: sysConfig.TOKEN_PREFIX + token,
      },
      responseType: "blob", //此属性非常重要，不然数据是乱码
    };
    config3.data = params;
    return new Promise((resolve, reject) => {
      request(config3)
        .then(resolve)
        .catch(reject);
    });
  } else {
    var config1 = {
      url: API_BASE_URL + opt.url,
      method: method,
      headers: {
        Authorization: sysConfig.TOKEN_PREFIX + token,
        ...(opt.headers || {}),
      },
    };
    method === "GET" && (config1.params = params);
    method === "POST" && (config1.data = params);
    method === "PATCH" && (config1.data = params);
    return new Promise((resolve, reject) => {
      request(config1)
        .then((res) => {
          resolve(res.data);
        })
        .catch((res) => {
          reject(res);
        });
    });
  }
}

function isEmpty(query) {
  return (
    query === "" ||
    query === null ||
    query === undefined ||
    (typeof query === "object" && Object.keys(query).length === 0)
  );
}

/**
 * 构建URL参数
 */
const buildUrlQuery = (baseUrl, queryParams) => {
  if (isEmpty(queryParams)) {
    return baseUrl;
  }

  const queryString = Object.entries(queryParams)
    .filter(([_, value]) => value !== undefined && value !== null)
    .map(
      ([key, value]) =>
        `${encodeURIComponent(key)}=${encodeURIComponent(value)}`,
    )
    .join("&");

  const turl = queryString ? `${baseUrl}?${queryString}` : baseUrl;
  return turl;
};

export function ajaxGet(opt) {
  return ajax(opt, "GET");
}
export function ajaxPut(opt) {
  return ajax(opt, "PUT");
}
export function ajaxDelete(opt) {
  return ajax(opt, "DELETE");
}
export function ajaxPost(opt) {
  return ajax(opt, "POST");
}
export function ajaxPatch(opt) {
  return ajax(opt, "PATCH");
}
// 单例详情获取get /api/test/12xxxxxxxx/
export function ajaxGetDetailByID(opt) {
  return ajax(opt, "GET2");
}
// 下载excel文件流（blob）
export function ajaxDownloadExcel(opt) {
  return ajax(opt, "excel");
}

//websocket获取jwt请求token
export function getJWTAuthorization() {
  var token = getToken();
  var jwt = "JWTlee" + token;
  return jwt;
}

export function downloadFile(param) {
  let token = getToken();
  return axios({
    method: "post",
    url: API_BASE_URL + param.url,
    headers: {
      Authorization: "JWT " + token,
    },
    data: param.params ? JSON.parse(JSON.stringify(param.params)) : null,
    responseType: "blob",
  }).then((res) => res);
}

export function getDownloadFile(param) {
  const urlParams = new URLSearchParams(param.params);
  let url = API_BASE_URL + param.url;
  url += "?" + urlParams.toString();
  window.location.href = url;
}

// 上传图片
export function uploadImg(param) {
  let formData = new FormData();
  formData.append("file", param.params.file);
  let token = getToken();
  return axios({
    method: "post",
    url: API_BASE_URL + param.url,
    headers: {
      "Content-Type": "multipart/form-data",
      Authorization: sysConfig.TOKEN_PREFIX + token,
    },
    data: formData,
    onUploadProgress: (progressEvent) => {
      // progressEvent.loaded:已上传文件大小
      // progressEvent.total:被上传文件的总大小
      let loadProgress = (progressEvent.loaded / progressEvent.total) * 100;
      if (param.params.onProgress) {
        param.params.onProgress({ percent: loadProgress });
      }
      // console.info(progressEvent.loaded)
      // console.info(progressEvent.total)
    },
  }).then((res) => res.data);
}

export function uploadFile(param, onProgress) {
  const token = getToken();
  return new Promise((resolve, reject) => {
    axios({
      method: "post",
      url: API_BASE_URL + param.url,
      headers: {
        "Content-Type": "multipart/form-data",
        Authorization: sysConfig.TOKEN_PREFIX + token,
      },
      data: param.formData,
      onUploadProgress: (progressEvent) => {
        if (onProgress) {
          onProgress(progressEvent);
        }
      },
    })
      .then((response) => {
        resolve(response.data);
      })
      .catch((error) => {
        reject(error);
      });
  });
}

export function uploadFileParams(param, onProgress) {
  const token = getToken();
  return new Promise((resolve, reject) => {
    axios({
      method: "post",
      url: API_BASE_URL + param.url,
      headers: {
        "Content-Type": "multipart/form-data",
        Authorization: sysConfig.TOKEN_PREFIX + token,
      },
      data: param.params.formData,
      onUploadProgress: (progressEvent) => {
        if (onProgress) {
          onProgress(progressEvent);
        }
      },
    })
      .then((response) => {
        resolve(response.data);
      })
      .catch((error) => {
        reject(error);
      });
  });
}
