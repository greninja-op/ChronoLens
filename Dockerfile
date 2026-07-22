# ChronoLens app image — runs either the demo store or Mission Control.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONPATH=/app/src

# Mission Control by default; docker-compose overrides `command` for the store.
EXPOSE 8090 8095
CMD ["python", "app.py"]
