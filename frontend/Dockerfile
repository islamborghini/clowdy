# Frontend image: build the Vite bundle, then serve the static files.
#
# Multi-stage on purpose. The build stage needs Node, npm, and ~300MB of
# node_modules; the runtime stage needs none of that. Only the compiled dist/
# crosses the boundary, so the shipped image is nginx plus a few hundred KB
# instead of the whole toolchain.

# --- Stage 1: build ---
FROM node:22-alpine AS build

WORKDIR /app

# package files first so npm ci is cached independently of source changes
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines env vars at build time, so these are build arguments rather
# than runtime ones.
#
# Docker will warn that a key is being passed through ARG/ENV. It is correct
# to warn in general and wrong here: a Clerk *publishable* key is public by
# design and ships inside the JavaScript bundle either way. The secret half is
# the Clerk secret key, which the backend reads from the environment at
# runtime and which never enters an image. Defaults to same-origin, which is what the
# nginx proxy below serves.
ARG VITE_API_URL=""
ARG VITE_CLERK_PUBLISHABLE_KEY=""
ARG VITE_DEMO_MODE="false"
ENV VITE_API_URL=$VITE_API_URL \
    VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY \
    VITE_DEMO_MODE=$VITE_DEMO_MODE
RUN npm run build

# --- Stage 2: serve ---
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# 127.0.0.1, not localhost: nginx here listens on IPv4 only, while localhost
# inside the container resolves to ::1 first, so the check would fail forever
# against a perfectly healthy server.
HEALTHCHECK --interval=30s --timeout=3s \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1
