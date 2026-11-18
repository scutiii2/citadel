# syntax=docker/dockerfile:1
# Build context is apps/: portcullis_admin imports two files from ember_web
# (PwaStatus.vue, pageLayout.css) by relative path.
FROM node:22-alpine AS build
WORKDIR /src/portcullis_admin
COPY portcullis_admin/package.json portcullis_admin/pnpm-lock.yaml portcullis_admin/pnpm-workspace.yaml* ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY portcullis_admin/ ./
COPY ember_web/src/components/layout/PwaStatus.vue ember_web/src/components/layout/pageLayout.css /src/ember_web/src/components/layout/
# The shared files resolve their imports (vue, virtual:pwa-register) from ember_web.
RUN ln -s /src/portcullis_admin/node_modules /src/ember_web/node_modules \
    && pnpm run build

FROM nginx:1.27-alpine
COPY --from=build /src/portcullis_admin/dist /usr/share/nginx/html
COPY portcullis_admin/nginx.conf /etc/nginx/templates/default.conf.template
ENV FRAME_ANCESTORS="'none'"
EXPOSE 80
