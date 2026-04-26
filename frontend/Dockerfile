# Stage 1 — Build React app
FROM node:20-alpine AS build

WORKDIR /app

# Copy package.json and lock file first (cached layer)
COPY package.json package-lock.json ./

RUN npm ci

COPY . .

# Inject API URL at build time for Vite
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL


# Build React for production
RUN npm run build

# Stage 2 — Serve with Nginx -- ( PRODUCTION READY )
FROM nginx:alpine

# Remove default Nginx static files
RUN rm -rf /usr/share/nginx/html/*

# Copy built React files from previous stage
COPY --from=build /app/dist /usr/share/nginx/html

# Expose HTTP port
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]