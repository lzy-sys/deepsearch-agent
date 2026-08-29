# syntax=docker/dockerfile:1
# ============================================================
# DeepSearch Agents - 前端构建 + Nginx 托管镜像
#   阶段一 build ：pnpm 构建 React 静态产物
#   阶段二 nginx ：托管静态产物并反代后端 /api 与 /ws
# ============================================================

FROM node:22-alpine AS build

WORKDIR /app

# 启用 corepack 并固定 pnpm 版本（与 package.json packageManager 对齐）
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
