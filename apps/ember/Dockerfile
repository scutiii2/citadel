# syntax=docker/dockerfile:1
# The browser build of Ember, served by nginx beside the other Citadel web apps. The Windows app (src-tauri) is built separately.
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml* ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY . ./
RUN pnpm run build

FROM nginx:1.27-alpine
COPY --from=build /src/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template
ENV FRAME_ANCESTORS="'none'"
EXPOSE 80
