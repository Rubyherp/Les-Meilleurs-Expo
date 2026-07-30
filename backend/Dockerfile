FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential python3-dev libglib2.0-0 libgl1 ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -c "import tomllib; data = tomllib.load(open('pyproject.toml', 'rb')); print(*data['build-system']['requires'], *data['project']['dependencies'], sep='\n')" \
    | pip install --requirement /dev/stdin

COPY README.md ./
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-build-isolation --no-deps .

# Model assets are provisioned separately at runtime/build time; they are not
# bundled in this repository or downloaded implicitly by the application.
RUN mkdir -p /service/models

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
