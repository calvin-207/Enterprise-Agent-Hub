<!--
description：侧边菜单彩色应用图标（与品牌 logo 同语言：圆角方块 + 多段渐变 + 白色图形）
菜单存的是 Element Plus 图标名（如 House/Setting），本组件将其渲染为
渐变小方块图标；lyicon- 前缀的自定义 SVG 保持原样渲染。
渐变为三段色阶（高光→主色→深色）+ 顶部辉光，接近大厂 app 图标质感。
未登记的图标名按名字哈希稳定取兜底渐变，新增菜单无需配置。
-->
<template>
	<span v-if="isEleIcon" class="menu-app-icon" :style="tileStyle">
		<el-icon class="menu-app-icon__glyph">
			<component :is="iconClass" />
		</el-icon>
	</span>
	<SvgIcon v-else-if="iconClass" :icon-class="iconClass" style="font-size: 18px;"></SvgIcon>
</template>

<script setup>
	import { computed } from 'vue'
	import SvgIcon from '@/components/icons/SvgIcon.vue'

	const props = defineProps({
		iconClass: {
			type: String,
			required: false,
			default: ''
		},
	})

	// 已知菜单图标 -> 三段渐变 [高光, 主色, 深色]（与 initialize.py 菜单种子对应）
	const GRADIENTS = {
		House: ['#7CB8FF', '#3D7BFF', '#2352D6'], // 工作台 - 品牌蓝
		Message: ['#6EE7B7', '#10B981', '#047857'], // 我的消息 - 绿
		ChatDotRound: ['#C4B5FD', '#8B5CF6', '#6D28D9'], // Agent 会话 - 紫罗兰
		Lightning: ['#FDBA74', '#F97316', '#DD5800'], // Agent 执行 - 橙
		Cpu: ['#A5B4FC', '#6366F1', '#4338CA'], // Agent 管理 - 靛蓝
		Timer: ['#FDE68A', '#F59E0B', '#D97706'], // 自动化任务 - 琥珀
		AlarmClock: ['#67E8F9', '#06B6D4', '#0E7490'], // 定时任务计划 - 青
		User: ['#F9A8D4', '#EC4899', '#DB2777'], // 个人中心/用户管理 - 玫红
		Setting: ['#CBD5E1', '#94A3B8', '#475569'], // 组织与权限/平台设置 - 岩灰蓝
		OfficeBuilding: ['#5EEAD4', '#14B8A6', '#0F766E'], // 部门管理 - 蓝绿
		UserFilled: ['#E9D5FF', '#A855F7', '#7E22CE'], // 角色管理 - 紫
		Menu: ['#AFC6EE', '#6B87C6', '#3A5590'], // 菜单管理 - 蓝钢青
		Lock: ['#7DD3FC', '#0EA5E9', '#0369A1'], // 权限管理 - 天蓝
		Document: ['#D9F99D', '#84CC16', '#4D7C0F'], // 操作日志 - 青柠
		Tickets: ['#FCA5A5', '#EF4444', '#DC2626'], // 登录日志 - 红
		Tools: ['#D6D3D1', '#A8A29E', '#57534E'], // 系统配置 - 石墨
		MagicStick: ['#818CF8', '#7C3AED', '#581C87'], // AI 模型管理 - AI 蓝紫
		Reading: ['#F5C77E', '#DF9A3C', '#B06E18'], // 数据字典 - 蜜金
		Bell: ['#FEF08A', '#EAB308', '#CA8A04'], // 通知公告 - 金黄
		Monitor: ['#99F6E4', '#2DD4BF', '#0D9488'], // 运维管理 - 青绿
	}

	// 兜底渐变：未登记图标按名字哈希稳定取色
	const FALLBACK = [
		['#93C5FD', '#3B82F6', '#1D4ED8'],
		['#6EE7B7', '#10B981', '#047857'],
		['#F9A8D4', '#EC4899', '#BE185D'],
		['#FDE68A', '#F59E0B', '#B45309'],
		['#67E8F9', '#06B6D4', '#0E7490'],
		['#C4B5FD', '#8B5CF6', '#6D28D9'],
	]

	const isEleIcon = computed(() => {
		return !!props.iconClass && !props.iconClass.includes('lyicon-')
	})

	const gradient = computed(() => {
		const g = GRADIENTS[props.iconClass]
		if (g) return g
		let h = 0
		for (const c of props.iconClass) {
			h = (h * 31 + c.codePointAt(0)) >>> 0
		}
		return FALLBACK[h % FALLBACK.length]
	})

	const tileStyle = computed(() => {
		const [hi, mid, deep] = gradient.value
		return {
			backgroundImage: `radial-gradient(circle at 32% 26%, rgba(255,255,255,0.5) 0%, rgba(255,255,255,0) 46%), linear-gradient(137deg, ${hi} 0%, ${mid} 48%, ${deep} 100%)`,
		}
	})
</script>

<style scoped>
	.menu-app-icon {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		width: 20px;
		height: 20px;
		border-radius: 5px;
		margin-right: 6px;
		color: #fff;
		box-shadow:
			0 1px 2px rgba(0, 0, 0, 0.22),
			inset 0 0 0 0.5px rgba(255, 255, 255, 0.28);
		overflow: hidden;
	}

	/* 顶部玻璃高光，质感对齐 app 图标 */
	.menu-app-icon::before {
		content: '';
		position: absolute;
		inset: 0;
		border-radius: inherit;
		background: linear-gradient(180deg, rgba(255, 255, 255, 0.35) 0%, rgba(255, 255, 255, 0) 55%);
	}

	.menu-app-icon__glyph {
		position: relative;
		font-size: 12px;
		/* 覆盖 el-menu 对内部 .el-icon 的默认间距/宽度，避免破坏居中 */
		margin-right: 0 !important;
		width: auto !important;
	}

	/* 折叠菜单（仅图标）下去掉与文字的间距，保持居中 */
	.el-menu--collapse .menu-app-icon {
		margin-right: 0;
	}
</style>
