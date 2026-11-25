# syntax=docker/dockerfile:1
# One recipe for the five admin apps. The build context is the Citadel root, because the apps share
# libs/citadel_ui through the pnpm workspace. `--build-arg APP=<folder under apps/>` picks the app.
FROM node:22-alpine AS build
ARG APP
WORKDIR /src
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY libs/citadel_ui/package.json libs/citadel_ui/
COPY apps/armory_admin/package.json apps/armory_admin/
COPY apps/legion_admin/package.json apps/legion_admin/
COPY apps/portcullis_admin/package.json apps/portcullis_admin/
COPY apps/stronghold_admin/package.json apps/stronghold_admin/
COPY apps/treasury_admin/package.json apps/treasury_admin/
RUN corepack enable && pnpm install --frozen-lockfile --filter "./apps/${APP}..."
COPY libs/citadel_ui libs/citadel_ui
COPY apps/${APP} apps/${APP}
WORKDIR /src/apps/${APP}
RUN pnpm run build

FROM nginx:1.27-alpine
ARG APP
COPY --from=build /src/apps/${APP}/dist /usr/share/nginx/html
COPY apps/${APP}/nginx.conf /etc/nginx/templates/default.conf.template
ENV FRAME_ANCESTORS="'none'"
EXPOSE 80
