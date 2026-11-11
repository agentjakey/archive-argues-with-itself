# The Railway redirect service: a 301 for every request, to the same path and query on the new
# domain. No volume. Build context: this folder. Its host settings live in the host's dashboard; the
# repository has no railway.json or railway.toml.
FROM python:3.11-alpine
# The base image ships older pip, setuptools and wheel with published advisories; upgrade them first.
RUN pip install --no-cache-dir --upgrade pip==26.3 setuptools==84.2.1 wheel==0.48.0
WORKDIR /app
COPY redirect_app.py .
ENV PYTHONUNBUFFERED=1 REDIRECT_TARGET=https://archiveargues.org
USER nobody
EXPOSE 8080
CMD ["python", "redirect_app.py"]
