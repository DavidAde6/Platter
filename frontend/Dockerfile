# Stage 1 — Build React app
FROM node:24-alpine AS build

WORKDIR /app

# Copy package.json and lock file first (cached layer)
COPY package.json package-lock.json ./

RUN npm ci

COPY . .

# Inject API URL at build time for Vite
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
ARG VITE_BUILD_SHA


# Build React for production
RUN npm run build

# A tiny immutable release marker lets deployment verify that the public
# hostname is serving this exact frontend image, not a stale tunnel/container.
RUN printf '{\n  "commit": "%s"\n}\n' "$VITE_BUILD_SHA" > /app/dist/build.json

# Stage 2 — Serve with Nginx -- ( PRODUCTION READY )
FROM nginx:alpine

# Remove default Nginx static files
RUN rm -rf /usr/share/nginx/html/*

# Copy built React files from previous stage
COPY --from=build /app/dist /usr/share/nginx/html

# Production routing and proxying are supplied by deploy/nginx.conf at runtime.

# Expose HTTP port
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]
