# Shared image for the two stdlib-only lab services. The app file is chosen at runtime
# by the Compose service, so both stay on one pinned base layer.
FROM python:3.14.7-slim

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin drill

# Create the capture directory in the image and give it to the runtime user. Docker copies
# ownership from the image when it first populates a named volume, so doing this here is what
# lets the non-root receiver write. A volume mounted onto a root-owned path cannot be chowned
# by a process that is not root, which fails at startup rather than at first write.
RUN mkdir -p /captures && chown 10001:10001 /captures

WORKDIR /app
COPY target/app.py /app/target_app.py
COPY receiver/app.py /app/receiver_app.py

USER 10001:10001
EXPOSE 8080
CMD ["python", "/app/target_app.py"]
