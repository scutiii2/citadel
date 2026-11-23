# syntax=docker/dockerfile:1
# Build context is apps/ (the compose file points at it); only portcullis_admin is copied in.
FROM node:22-alpine AS build
WORKDIR /src/portcullis_admin
COPY portcullis_admin/package.json portcullis_admin/pnpm-lock.yaml portcullis_admin/pnpm-workspace.yaml* ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY portcullis_admin/ ./
RUN pnpm run build

FROM nginx:1.27-alpine
COPY --from=build /src/portcullis_admin/dist /usr/share/nginx/html
COPY portcullis_admin/nginx.conf /etc/nginx/templates/default.conf.template
ENV FRAME_ANCESTORS="'none'"
EXPOSE 80
