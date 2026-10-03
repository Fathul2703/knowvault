# --- Development: source bind-mounted, hot reload ------------------------------------------------
FROM node:22-alpine AS dev

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]

# --- Production build --------------------------------------------------------------------------
FROM node:22-alpine AS build

# Rewrites are fixed at build time. Behind the production proxy /api/* never reaches Next.js;
# this only matters when the web container is reached directly (e.g. the E2E stack).
ARG API_INTERNAL_URL=http://api:8000
ENV NEXT_TELEMETRY_DISABLED=1 \
    API_INTERNAL_URL=$API_INTERNAL_URL
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# --- Production: the standalone server only ------------------------------------------------------
FROM node:22-alpine AS prod

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app

COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static

USER node
EXPOSE 3000
CMD ["node", "server.js"]
