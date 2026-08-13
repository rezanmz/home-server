# syntax=docker/dockerfile:1.25
# renovate: datasource=docker depName=node versioning=node
FROM node:24-bookworm-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY lib.js server.js ./
COPY test ./test
RUN npm test && rm -rf test

USER node
EXPOSE 8080
CMD ["node", "server.js"]
