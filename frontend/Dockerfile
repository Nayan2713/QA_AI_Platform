# # ==============================================================================
# # React Frontend Dockerfile - Multi-Stage Build
# # ==============================================================================

# # --- Stage 1: Base and Dependencies ---
# FROM node:20-slim AS base

# WORKDIR /app

# # Cache dependencies
# COPY package*.json /app/
# RUN npm install

# # Copy source files
# COPY . /app/

# # --- Stage 2: Development Target (Vite dev server) ---
# FROM base AS development
# EXPOSE 3000
# CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]

# # --- Stage 3: Build Production Assets ---
# FROM base AS builder
# # Inject Vite backend API URL at build time if provided
# ARG VITE_API_URL
# ENV VITE_API_URL=$VITE_API_URL
# RUN npm run build

# # --- Stage 4: Production Serve via Nginx ---
# FROM nginx:1.25-alpine-slim AS production

# # Copy custom default Nginx configuration
# COPY nginx.conf /etc/nginx/conf.d/default.conf

# # Copy production built static assets from builder stage
# COPY --from=builder /app/dist /usr/share/nginx/html

# EXPOSE 80

# CMD ["nginx", "-g", "daemon off;"]
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .

ARG VITE_API_URL=/api/
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]