# ==============================================================================
# React Frontend Dockerfile - Multi-Stage Build
# ==============================================================================

# --- Stage 1: Base and Dependencies ---
FROM node:20-alpine AS base
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .

# --- Stage 2: Development Target (Vite dev server) ---
FROM base AS development
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]

# --- Stage 3: Build Production Assets ---
FROM base AS builder
ARG VITE_API_URL=/api/
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# --- Stage 4: Production Serve via Nginx ---
FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]