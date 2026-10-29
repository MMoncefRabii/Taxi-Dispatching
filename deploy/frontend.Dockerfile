FROM node:22.22.2-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/index.html frontend/platform.html frontend/invite.html ./
COPY frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src

ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM caddy:2.10.2-alpine

COPY --from=build /app/dist /srv
COPY deploy/Caddyfile /etc/caddy/Caddyfile
