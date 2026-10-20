# ==============================================================================
# frontend/Dockerfile
# Multi-stage production build for Vite + React with Nginx reverse proxy
# ==============================================================================

# Stage 1: Build production React/TypeScript bundle
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency manifests and install packages
COPY package.json package-lock.json ./
RUN npm ci

# Copy frontend source code and configuration
COPY . .

# Build-time environment variables for Vite bundle
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_USE_MOCK=false
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_USE_MOCK=$VITE_USE_MOCK

# Build optimized static distribution
RUN npm run build

# Stage 2: Serve production bundle with lightweight Nginx
FROM nginx:alpine

# Remove default nginx welcome page
RUN rm -rf /usr/share/nginx/html/*

# Copy built production assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration with reverse proxy for /api/
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose HTTP port
EXPOSE 80

# Launch Nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
