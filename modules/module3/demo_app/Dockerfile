FROM python:3.12-slim
WORKDIR /app
COPY main.py .
ENV PYTHONUNBUFFERED=1
EXPOSE 8082
HEALTHCHECK --interval=15s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8082/health')"
CMD ["python", "main.py"]
