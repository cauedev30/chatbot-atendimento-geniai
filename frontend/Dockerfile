# The board: next build in a build stage, next start in the final one. Build context: frontend/.
# BACKEND_URL is read at build time (the /api proxy in next.config.ts) and at start (server rendering),
# so it is a build argument and an environment variable; rebuild when it changes.

FROM node:24-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:24-slim AS build
WORKDIR /app
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# public/ may be absent from a clone (git keeps no empty folder); next start serves it when present.
RUN mkdir -p public && npm run build && npm prune --omit=dev --no-audit --no-fund

FROM node:24-slim
WORKDIR /app
ARG BACKEND_URL=http://backend:8000
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    BACKEND_URL=$BACKEND_URL \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=build --chown=node:node /app/package.json ./package.json
COPY --from=build --chown=node:node /app/next.config.ts ./next.config.ts
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/.next ./.next
USER node
EXPOSE 3000
# next start listens on PORT.
CMD ["node_modules/.bin/next", "start"]
