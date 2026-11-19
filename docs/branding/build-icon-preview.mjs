// 从本地 @element-plus/icons-vue 的 global bundle 提取图标 path 数据，
// 生成完全离线的菜单图标设计预览页（静态 HTML，无需 CDN/Vue）。
// 用法：node docs/branding/build-icon-preview.mjs
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const src = readFileSync(
	resolve(here, '../../frontend/node_modules/@element-plus/icons-vue/dist/global.js'),
	'utf8',
)

// 提取 { "House": ["M...", ...] } —— 定义处为 `\n  name: "Xxx",`，与 `__name` 区分
const icons = {}
const anchors = [...src.matchAll(/\n  name: "(\w+)",/g)]
for (let i = 0; i < anchors.length; i++) {
	const name = anchors[i][1]
	const start = anchors[i].index + 1
	const end = i + 1 < anchors.length ? anchors[i + 1].index + 1 : start + 3000
	const ds = [...src.slice(start, end).matchAll(/d: "([^"]+)"/g)].map((x) => x[1])
	if (ds.length && !icons[name]) icons[name] = ds
}

// 与 frontend/src/layout/components/MenuIcon.vue 保持一致
const GRADIENTS = {
	House: ['#7CB8FF', '#3D7BFF', '#2352D6'],
	Message: ['#6EE7B7', '#10B981', '#047857'],
	ChatDotRound: ['#C4B5FD', '#8B5CF6', '#6D28D9'],
	Lightning: ['#FDBA74', '#F97316', '#DD5800'],
	Cpu: ['#A5B4FC', '#6366F1', '#4338CA'],
	Timer: ['#FDE68A', '#F59E0B', '#D97706'],
	AlarmClock: ['#67E8F9', '#06B6D4', '#0E7490'],
	User: ['#F9A8D4', '#EC4899', '#DB2777'],
	Setting: ['#CBD5E1', '#94A3B8', '#475569'],
	OfficeBuilding: ['#5EEAD4', '#14B8A6', '#0F766E'],
	UserFilled: ['#E9D5FF', '#A855F7', '#7E22CE'],
	Menu: ['#AFC6EE', '#6B87C6', '#3A5590'],
	Lock: ['#7DD3FC', '#0EA5E9', '#0369A1'],
	Document: ['#D9F99D', '#84CC16', '#4D7C0F'],
	Tickets: ['#FCA5A5', '#EF4444', '#DC2626'],
	Tools: ['#D6D3D1', '#A8A29E', '#57534E'],
	MagicStick: ['#818CF8', '#7C3AED', '#581C87'],
	Reading: ['#F5C77E', '#DF9A3C', '#B06E18'],
	Bell: ['#FEF08A', '#EAB308', '#CA8A04'],
}

const MENUS = [
	{ icon: 'House', title: '工作台', active: true },
	{ icon: 'Message', title: '我的消息' },
	{ icon: 'ChatDotRound', title: 'Agent 会话' },
	{ icon: 'Lightning', title: 'Agent 执行' },
	{ icon: 'Cpu', title: 'Agent 管理' },
	{ icon: 'Timer', title: '自动化任务' },
	{ icon: 'AlarmClock', title: '定时任务计划' },
	{ icon: 'User', title: '个人中心' },
	{ icon: 'Setting', title: '组织与权限', group: [
		{ icon: 'User', title: '用户管理' },
		{ icon: 'OfficeBuilding', title: '部门管理' },
		{ icon: 'UserFilled', title: '角色管理' },
		{ icon: 'Menu', title: '菜单管理' },
		{ icon: 'Lock', title: '权限管理' },
		{ icon: 'Document', title: '操作日志' },
		{ icon: 'Tickets', title: '登录日志' },
	]},
	{ icon: 'Tools', title: '系统配置', group: [
		{ icon: 'MagicStick', title: 'AI 模型管理' },
		{ icon: 'Setting', title: '平台设置' },
		{ icon: 'Reading', title: '数据字典' },
		{ icon: 'Bell', title: '通知公告' },
	]},
]

const tile = (icon, cls = '') => {
	const [hi, mid, deep] = GRADIENTS[icon]
	const paths = (icons[icon] || [])
		.map((d) => `<path fill="currentColor" d="${d}"/>`)
		.join('')
	return `<span class="menu-app-icon ${cls}" style="background-image:radial-gradient(circle at 32% 26%, rgba(255,255,255,.5) 0%, rgba(255,255,255,0) 46%), linear-gradient(137deg, ${hi} 0%, ${mid} 48%, ${deep} 100%)"><svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">${paths}</svg></span>`
}

const row = (item, sub = false) =>
	`<div class="${sub ? 'sub-item' : 'menu-item'}${item.active ? ' active' : ''}">${tile(item.icon)}${item.title}</div>`

const menuHtml = MENUS.map((m) => {
	let out = row(m)
	if (m.group) {
		out += `<div class="group-title">${m.title}</div>`
		out += m.group.map((c) => row(c, true)).join('')
	}
	return out
}).join('')

const collapsedHtml = MENUS.map((m) => tile(m.icon)).join('')

const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Enterprise Agent Hub - 菜单图标设计预览</title>
<style>
	* { box-sizing: border-box; margin: 0; padding: 0; }
	body {
		font-family: "Helvetica Neue", Helvetica, "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
		background: #eef1f6;
		padding: 32px;
		display: flex;
		gap: 36px;
		align-items: flex-start;
		flex-wrap: wrap;
	}
	.caption { width: 100%; color: #475569; font-size: 14px; margin-bottom: 4px; }
	.caption strong { color: #1e293b; font-size: 18px; }

	.sidebar { width: 224px; border-radius: 10px; overflow: hidden; box-shadow: 0 12px 32px rgba(15,23,42,.14); }
	.sidebar.light { background: #fff; }
	.sidebar.dark { background: #272E39; }

	.side-head { height: 56px; display: flex; align-items: center; gap: 10px; padding: 0 16px; }
	.light .side-head { border-bottom: 1px solid #f0f0f0; }
	.dark .side-head { background: #1f2530; }
	.side-head img { width: 28px; height: 28px; border-radius: 7px; }
	.light .side-head span { font-weight: 600; font-size: 13.5px; color: #303133; }
	.dark .side-head span { font-weight: 600; font-size: 13.5px; color: #fff; }

	.menu { padding: 8px; }
	.menu-item { height: 46px; display: flex; align-items: center; padding: 0 12px; border-radius: 6px; margin-bottom: 2px; font-size: 14px; }
	.light .menu-item { color: #303133; }
	.dark .menu-item { color: #cfd3dc; }
	.light .menu-item:hover { background: #f5f7fa; }
	.dark .menu-item:hover { background: rgba(255,255,255,.06); }
	.light .menu-item.active { background: #ecf2ff; color: #3A7BFF; font-weight: 600; }
	.dark .menu-item.active { background: rgba(58,123,255,.18); color: #8fb5ff; font-weight: 600; }

	.group-title { margin: 10px 0 4px 14px; font-size: 12px; opacity: .5; }
	.sub-item { height: 40px; display: flex; align-items: center; padding: 0 12px 0 16px; border-radius: 6px; margin-bottom: 2px; font-size: 13.5px; }
	.light .sub-item { color: #606266; }
	.dark .sub-item { color: #a3abb8; }
	.light .sub-item:hover { background: #f5f7fa; }
	.dark .sub-item:hover { background: rgba(255,255,255,.06); }

	/* ===== MenuIcon 核心（与 frontend/src/layout/components/MenuIcon.vue 一致） ===== */
	.menu-app-icon {
		position: relative; display: inline-flex; align-items: center; justify-content: center;
		flex-shrink: 0; width: 20px; height: 20px; border-radius: 5px; margin-right: 8px;
		color: #fff; overflow: hidden;
		box-shadow: 0 1px 2px rgba(0,0,0,.22), inset 0 0 0 .5px rgba(255,255,255,.28);
	}
	.menu-app-icon::before {
		content: ''; position: absolute; inset: 0; border-radius: inherit;
		background: linear-gradient(180deg, rgba(255,255,255,.35) 0%, rgba(255,255,255,0) 55%);
	}
	.menu-app-icon svg { width: 12px; height: 12px; position: relative; }
	.sub-item .menu-app-icon { width: 18px; height: 18px; border-radius: 4.5px; }
	.sub-item .menu-app-icon svg { width: 11px; height: 11px; }

	.collapsed {
		width: 64px; background: #fff; border-radius: 10px; box-shadow: 0 12px 32px rgba(15,23,42,.14);
		padding: 14px 0; display: flex; flex-direction: column; align-items: center; gap: 15px;
	}
	.collapsed .menu-app-icon { margin-right: 0; width: 22px; height: 22px; border-radius: 5.5px; }
	.collapsed .menu-app-icon svg { width: 13px; height: 13px; }
</style>
</head>
<body>
	<div class="caption"><strong>菜单图标设计预览</strong> —— 三段渐变圆角方块 + 白色线性图标（与品牌 logo 同语言）：亮色 / 暗色侧边栏 / 折叠态</div>
	<div class="sidebar light">
		<div class="side-head"><img src="logo-1024.png"><span>Enterprise Agent Hub</span></div>
		<div class="menu">${menuHtml}</div>
	</div>
	<div class="sidebar dark">
		<div class="side-head"><img src="logo-1024.png"><span>Enterprise Agent Hub</span></div>
		<div class="menu">${menuHtml}</div>
	</div>
	<div class="collapsed">${collapsedHtml}</div>
</body>
</html>
`

const missing = Object.keys(GRADIENTS).filter((k) => !icons[k])
if (missing.length) {
	console.error('missing icons:', missing.join(', '))
	process.exit(1)
}

writeFileSync(resolve(here, 'menu-icon-preview.html'), html)
console.log('written: docs/branding/menu-icon-preview.html,', Object.keys(icons).length, 'icons extracted')
