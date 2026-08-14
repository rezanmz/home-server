FROM ghcr.io/esphome/esphome:2026.7.4@sha256:e636269c6390c2124916510d45f55febb1d9ce41365f8445c9083ee41e43c92b

WORKDIR /work
COPY apps/cyd-ota/dashboard.yaml dashboard.yaml
COPY images/cyd-ota/secrets.yaml secrets.yaml

# Precompile the exact hardware and component set so the in-cluster updater
# needs only its private LAN egress when a rendered dashboard changes.
RUN esphome compile dashboard.yaml \
 && rm dashboard.yaml secrets.yaml \
 && chown -R 1000:1000 /work

USER 1000:1000
