# Stage 1 — Build React frontend
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2 — Nginx with built frontend
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
