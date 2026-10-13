# Runtime for the automation CLI and the Prometheus exporter.
FROM python:3.12-slim
WORKDIR /lab
COPY automation/requirements-dev.txt automation/requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt
ENV PYTHONPATH=/lab PYTHONUNBUFFERED=1
CMD ["python", "-m", "automation", "--help"]
