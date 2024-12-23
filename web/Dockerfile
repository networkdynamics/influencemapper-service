FROM python:3.10
LABEL authors="blodstone"

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100 \
  # Poetry's configuration:
  POETRY_VIRTUALENVS_CREATE=false \
  POETRY_NO_INTERACTION=1 \
  POETRY_CACHE_DIR='/var/cache/pypoetry' \
  POETRY_HOME='/usr/local' \
  LOG_LEVEL=info

WORKDIR /app

RUN pip install poetry
COPY ../pyproject.toml ../poetry.lock ../README.md ./../

RUN poetry install --no-root --with web
EXPOSE 8000

ENTRYPOINT ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]