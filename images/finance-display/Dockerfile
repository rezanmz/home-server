# syntax=docker/dockerfile:1.25
# renovate: datasource=docker depName=node versioning=node
FROM node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY lib.js server.js ./
COPY test ./test
RUN npm test && rm -rf test

USER node
EXPOSE 8080
CMD ["node", "server.js"]
