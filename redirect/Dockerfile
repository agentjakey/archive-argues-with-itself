# The Railway redirect service: a 301 for every request, to the same path and query on the new
# domain. No volume. Build context: this folder. Its host settings live in the host's dashboard; the
# repository has no railway.json or railway.toml.
FROM python:3.11-alpine
WORKDIR /app
COPY redirect_app.py .
ENV PYTHONUNBUFFERED=1 REDIRECT_TARGET=https://archiveargues.org
USER nobody
EXPOSE 8080
CMD ["python", "redirect_app.py"]
