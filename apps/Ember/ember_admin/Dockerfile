# syntax=docker/dockerfile:1
# Build context is apps/Ember: ember_admin imports two files from ember_web
# (PwaStatus.vue, pageLayout.css) by relative path.
FROM node:22-alpine AS build
WORKDIR /src/ember_admin
COPY ember_admin/package.json ember_admin/package-lock.json ./
RUN npm ci
COPY ember_admin/ ./
COPY ember_web/src/components/layout/PwaStatus.vue ember_web/src/components/layout/pageLayout.css /src/ember_web/src/components/layout/
# The shared files resolve their imports (vue, virtual:pwa-register) from ember_web.
RUN ln -s /src/ember_admin/node_modules /src/ember_web/node_modules \
    && npm run build

FROM nginx:1.27-alpine
COPY --from=build /src/ember_admin/dist /usr/share/nginx/html
COPY ember_admin/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
