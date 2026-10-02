# syntax=docker/dockerfile:1.25
# renovate: datasource=docker depName=node versioning=node
FROM node:24-bookworm-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03 AS build

# @actual-app/api 26.10.0 pulls better-sqlite3 13, whose linux binaries are
# built from source (no prebuilds); the slim base ships no toolchain, so the
# build stage installs one and only its artifacts reach the runtime image.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY lib.js server.js ./
COPY test ./test
RUN npm test && rm -rf test

FROM node:24-bookworm-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03

WORKDIR /app
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./
COPY lib.js server.js ./

USER node
EXPOSE 8080
CMD ["node", "server.js"]
