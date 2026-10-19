FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN useradd -m appuser && chown -R appuser /app
USER appuser
ENV TS_HOST=0.0.0.0 PORT=8000
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT','8000')}/api/health\")" || exit 1
CMD ["python", "run.py"]
