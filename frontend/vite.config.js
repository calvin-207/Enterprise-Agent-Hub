import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { createSvgIconsPlugin } from 'vite-plugin-svg-icons'
import VueSetupExtend from 'vite-plugin-vue-setup-extend'
import { resolve } from 'path';
import http from 'node:http';

const pathResolve = (dir) => {
    return resolve(__dirname, '.', dir);
};

let alias = {
    '@': pathResolve('./src/'),
}

// 开发环境路径处理：根路径 / 为官网 SEO 落地页，管理控制台入口在 /app/（与线上 Django 路由保持一致，对应 app.html）
// 落地页文案由 Django 服务端注入模板变量，因此开发时把 / 代理到后端 9999 渲染；后端未启动时回退为源文件
const BACKEND_ORIGIN = 'http://127.0.0.1:9999';

function proxyLandingToBackend(req, res, next) {
    const proxyReq = http.request(
        `${BACKEND_ORIGIN}${req.url}`,
        {
            method: req.method,
            headers: { ...req.headers, host: '127.0.0.1:9999' },
        },
        (proxyRes) => {
            res.writeHead(proxyRes.statusCode, proxyRes.headers);
            proxyRes.pipe(res);
        }
    );
    // 后端不可用时回退到 Vite 静态源文件（模板变量会以 {{ }} 原样展示，启动后端后即恢复）
    proxyReq.on('error', () => { next(); });
    req.pipe(proxyReq);
}

function devAppPathRewrite() {
    return {
        name: 'dev-app-path-rewrite',
        configureServer(server) {
            server.middlewares.use((req, res, next) => {
                const pathname = (req.url || '').split('?')[0];
                if (pathname === '/app' || pathname === '/app/') {
                    req.url = '/app.html';
                    return next();
                }
                if (pathname === '/') {
                    return proxyLandingToBackend(req, res, next);
                }
                next();
            });
        },
    };
}

export default defineConfig({
    plugins: [
        vue(),
        devAppPathRewrite(),
        VueSetupExtend(),
        createSvgIconsPlugin({
            iconDirs: [resolve(process.cwd(), 'src/assets/lee/icons/svg')], // 你的 SVG 目录
            symbolId: 'icon-[name]', // 格式必须和 `iconName` 计算属性匹配
        }),
    ],
    base: '/', // index.html文件所在位置
    root: './', // js导入的资源路径，src
    minify: true, // 是否压缩代码
    server: {
        https: false,//是否开启 HTTPS
        host: true, // host: "0.0.0.0" 设置 host: true 才可以使用 Network 的形式，以 IP 访问项目
        port: 8081,
        hmr: true,
        open: false, //是否自动打开浏览器
        cors: true,  //跨域设置允许
        strictPort: true, //端口被占用时，是否直接退出
        overlay: false,
        proxy: {
            // 将 /api 和 /media 开头的请求代理到后端开发服务器
            '/api': {
                target: 'http://127.0.0.1:9999',
                changeOrigin: true,
            },
            '/media': {
                target: 'http://127.0.0.1:9999',
                changeOrigin: true,
            },
        },
    },
    build: {
        // cssCodeSplit: false,//不分割css
        target: 'esnext', // 允许使用顶级 await
        minify: 'terser', // 是否进行压缩,boolean | 'terser' | 'esbuild',默认使用terser
        manifest: false,
        sourcemap: false,
        outDir: 'dist',
        emptyOutDir: true, // 构建前清空输出目录
        assetsDir: 'static',
        chunkSizeWarningLimit: 2000,
        terserOptions: {
            output: {
                ecma: 2015,
                comments: false,// 移除注释
                ascii_only: true,
            },
            compress: {
                drop_console: true, // 生产环境移除console
                drop_debugger: true,
            },
            mangle: true, // 启用名称混淆
        },
        // 多页应用：/ 官网 SEO 落地页（index.html）+ /app/ 管理控制台 SPA 入口（app.html）
        rollupOptions:{
            input: {
                index: resolve(__dirname, 'index.html'),
                app: resolve(__dirname, 'app.html'),
            },
            output:{
                entryFileNames: `static/[name].[hash].js`,
                chunkFileNames: `static/[name].[hash].js`,
                assetFileNames: `static/[name].[hash].[ext]`,
                manualChunks(id){
                    if (id.includes('node_modules')) {
                        return id.toString().split('node_modules/')[1].split('/')[0].toString();
                    }
                }
            }
        }
    },
    resolve: {
        alias,
    },
    css: {//sass2.0版本以上，消除警告
        preprocessorOptions: {
            scss: {
                api: 'modern-compiler', // or 'modern'
            },
        },
    },
})
