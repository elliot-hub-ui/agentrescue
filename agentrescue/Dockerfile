FROM python:3.12-slim
ENV HOST=0.0.0.0 PORT=10000 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY app.py MCP.md README.md ./
RUN useradd --uid 10001 --no-create-home app
USER app
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:10000/health',timeout=2)"
CMD ["python", "app.py"]
