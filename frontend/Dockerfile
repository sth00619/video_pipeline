FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json .
# Rollup's platform binary is an optional dependency.  The lockfile is also
# used on Windows during local development, so explicitly keep Alpine's musl
# binary in the image instead of letting npm omit it during a cross-platform
# Docker build.
RUN npm install --include=optional && \
    ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
      npm install --no-save @rollup/rollup-linux-x64-musl; \
    elif [ "$ARCH" = "aarch64" ]; then \
      npm install --no-save @rollup/rollup-linux-arm64-musl; \
    fi
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
# Copy both: template (for Railway/cloud) and default (for local Docker)
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
# nginx docker image auto-processes /etc/nginx/templates/ via envsubst on startup
