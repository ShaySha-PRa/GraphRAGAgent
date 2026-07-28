# CLAUDE.md

## 启动命令

```bash
cd frontend
npm install        # 首次或新增依赖后
npm run dev        # 启动开发服务器 → http://localhost:5173
npm run build      # 生产构建 → dist/
```

## 路径

```
frontend/          # 项目根目录
├── src/
│   ├── main.tsx        # 入口
│   ├── App.tsx         # 路由定义
│   ├── lib/            # api.ts（后端调用）+ types.ts（类型定义）
│   ├── styles/         # tokens.css + global.css
│   ├── components/     # 可复用组件
│   └── pages/          # 页面组件
```

## 技术栈

React 18 + Vite + TypeScript，纯 CSS（无 Tailwind/MUI）。

依赖：`react-router-dom`（路由）、`vis-network`（知识图谱渲染）、`react-markdown`（问答 Markdown 渲染）。

## 后端连接

默认连接 `http://127.0.0.1:8000`（`backend/` FastAPI 服务）。
可通过环境变量 `VITE_API_BASE_URL` 覆盖。
