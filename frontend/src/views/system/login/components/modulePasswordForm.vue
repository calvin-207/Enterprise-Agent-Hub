<template>
	<el-form ref="loginFormRef" :model="formData" :rules="rules" label-width="0" size="large" @keyup.enter="submitLogin" :disabled="islogining">
		<el-form-item prop="username">
			<el-input v-model="formData.username" prefix-icon="user" clearable placeholder="请输入用户名">
			</el-input>
		</el-form-item>
		<el-form-item prop="password">
			<el-input v-model="formData.password" prefix-icon="lock" clearable show-password placeholder="请输入密码"></el-input>
		</el-form-item>
		<el-form-item class="remember-item">
			<div class="remember-options">
				<el-checkbox v-model="rememberAccount" @change="handleRememberAccountChange">记住账号</el-checkbox>
				<el-checkbox v-model="rememberPassword" @change="handleRememberPasswordChange">记住密码</el-checkbox>
			</div>
		</el-form-item>
		<el-form-item prop="captcha" v-if="userState.sysConfig.loginCaptcha">
            <el-input type="text" prefix-icon="circle-check" v-model.trim="formData.captcha" auto-complete="off" placeholder="验证码" :rules="userState.sysConfig.loginCaptcha?captchaRules:[]">
                  <template #append>
                    <lee-img class="login-captcha" :src="image_base" @click="getCaptchas" />
                  </template>
            </el-input>
          </el-form-item>
		<el-form-item>
			<el-button type="primary" class="login-btn" style="width: 100%;" :loading="islogining" round @click="submitLogin">登录</el-button>
		</el-form-item>
	</el-form>
</template>

<script setup>
	import {ref, onMounted,watch,computed ,nextTick} from 'vue'
	import {autoStorage,setToken,setRefreshToken} from '@/utils/util'
	import CryptoJS from 'crypto-js'
	import Cookies from 'js-cookie'
	import { ElMessage } from 'element-plus'
	import { useRouter,useRoute } from 'vue-router'
	import Api from "@/api/api"
	import sysConfig from "@/config"
	import {useUserState} from "@/store/userState";
	import { useTabsStore } from '@/store/tabs'

	const userState = useUserState()

	// let API_BASE_URL = sysConfig.API_URL

	// // 当前是生产环境
	// if (import.meta.env.PROD) {
	// 	// 获取浏览器地址
	// 	API_BASE_URL = window.location.origin;
	// }
	const API_BASE_URL = window.location.origin

	const router = useRouter()

	let formData = ref({
		username: "",
		password: "",
		captcha: "",
		captchaKey: null,
	})
	let image_base = ref(null)
	let captchaRules = [
		{required: true, message: "请输入验证码", trigger: 'blur'}
	]
	let rules = ref({
		username: [
			{required: true, message: "请输入账号", trigger: 'blur'}
		],
		password: [
			{required: true, message: "请输入密码", trigger: 'blur'}
		]
	})
	let islogining = ref(false)

	// ========== 记住账号 / 记住密码 ==========
	// 存储在 Cookie 中（退出登录会清空 localStorage，但不会清除 Cookie），有效期 30 天
	const REMEMBER_KEY = 'rememberLoginInfo'
	const REMEMBER_EXPIRES = 30

	let rememberAccount = ref(false)
	let rememberPassword = ref(false)

	// 勾选"记住密码"时，自动勾选"记住账号"
	function handleRememberPasswordChange(val) {
		if (val) rememberAccount.value = true
	}

	// 取消"记住账号"时，自动取消"记住密码"
	function handleRememberAccountChange(val) {
		if (!val) rememberPassword.value = false
	}

	// 页面加载时回填记住的账号密码
	// 注意：这里用 CryptoJS 口令形式（EvpKDF 派生密钥）而非 util.js 的 crypto.AES，
	// 因为 LS_ENCRYPTION_KEY 为 25 字节，不是合法的 AES 密钥长度，后者加解密不对称
	function initRememberInfo() {
		try {
			const saved = Cookies.get(REMEMBER_KEY)
			if (!saved) return
			const info = JSON.parse(saved)
			if (info.rememberPassword && info.username && info.password) {
				formData.value.username = info.username
				const password = CryptoJS.AES.decrypt(info.password, sysConfig.LS_ENCRYPTION_KEY).toString(CryptoJS.enc.Utf8)
				formData.value.password = password || ''
				rememberAccount.value = true
				rememberPassword.value = true
			} else if (info.rememberAccount && info.username) {
				formData.value.username = info.username
				rememberAccount.value = true
			}
		} catch (e) {
			// 数据异常时清除，避免影响登录
			Cookies.remove(REMEMBER_KEY)
		}
	}

	// 登录成功后保存/清除记住信息（密码 AES 加密存储，避免明文落盘）
	function saveRememberInfo() {
		if (rememberPassword.value) {
			Cookies.set(REMEMBER_KEY, JSON.stringify({
				username: formData.value.username,
				password: CryptoJS.AES.encrypt(formData.value.password, sysConfig.LS_ENCRYPTION_KEY).toString(),
				rememberAccount: true,
				rememberPassword: true,
			}), { expires: REMEMBER_EXPIRES })
		} else if (rememberAccount.value) {
			Cookies.set(REMEMBER_KEY, JSON.stringify({
				username: formData.value.username,
				rememberAccount: true,
				rememberPassword: false,
			}), { expires: REMEMBER_EXPIRES })
		} else {
			Cookies.remove(REMEMBER_KEY)
		}
	}

	/**
	* 获取验证码
	*/
	function getCaptchas () {
		Api.getCaptcha().then((res) => {
			if(res.code == 2000){
				formData.value.captcha = null
				formData.value.captchaKey = res.data.key
				image_base.value = res.data.image_base
			}else{
				ElMessage.error(res.msg)
			}
		})
	}

	let loginFormRef = ref(null)

	const submitLogin = async () => {
		if (islogining.value) return; // 防止重复提交

		try {
			islogining.value = true; // 开启加载状态

			// 1. 表单验证
			await loginFormRef.value.validate();

			// 2. 调用登录接口（重点修改部分）
			const res = await Api.getToken(formData.value);
    
			if (res.code === 2000) {
				islogining.value = true
				// 3. 登录成功处理
				saveRememberInfo()
				setToken('logintoken', res.data.access);
				setRefreshToken('refreshtoken', res.data.refresh);
				await userState.getSystemWebRouter(router)
				loginSuccess(); // 执行跳转等操作
				ElMessage.success('登录成功');

				islogining.value = false
			} else {
				// 4. 登录失败（服务端返回错误）
				ElMessage.error(res.msg || '登录失败');
				getCaptchas(); // 刷新验证码
			}

		} catch (error) {
			// 区分验证失败和请求失败
			if (error.fields) {
				ElMessage.warning('请填写正确的登录信息');
			} else {
				ElMessage.error('登录失败，请重试');
			}
		} finally {
			islogining.value = false; // 关闭加载状态
		}
	}

	function getCacheActiveTab(){
		let tabsStore = useTabsStore()
		return tabsStore.activeTab
	}

	function loginSuccess(){
		let firstpath = getCacheActiveTab()
		if(!firstpath){
			window.location.href = API_BASE_URL+"/#/"
		}else{
			router.push(firstpath);
		}
		
	}

	onMounted(()=>{
		//回填记住的账号密码
		initRememberInfo()
		//请求数据
		getCaptchas()
	})

</script>

<style scoped>
	.remember-item{
		margin-bottom: 14px;
	}
	.remember-options{
		display: flex;
		align-items: center;
		gap: 16px;
		width: 100%;
		height: 24px;
	}
	.login-captcha{
		cursor: pointer;
		height: 38px;
		width: 128px;
		display: block;
		margin: 0px -19px;
		border-top-right-radius: 2px;
		border-bottom-right-radius: 2px;
	}
	.login-btn{
		margin-top: 10px;
	}
</style>