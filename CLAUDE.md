# CLAUDE.md

## 项目结构

```
frontend/    # 所有前端代码（React + Vite + TypeScript）
backend/     # 所有后端代码（FastAPI + Python）
```

## 后端配置管理

- 所有外部配置（API Key、Base URL 等）统一放在 `.env` 文件中管理
- `.env` 严禁提交到 Git，已在 `.gitignore` 中忽略

## 后端虚拟环境

- 每个后端组件（`backend/`、`mineru-pipeline/`、`langextract_src/` 等）必须使用 `uv` 创建独立的虚拟环境（`.venv/`）
- `.venv/` 目录已在 `.gitignore` 中忽略
