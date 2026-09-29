# Development image. A production stage is planned for Phase 4 (see docs/ARCHITECTURE.md).
FROM node:22-alpine AS dev

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]
