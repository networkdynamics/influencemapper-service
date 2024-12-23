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
  POETRY_HOME='/usr/local'

WORKDIR /myapp

RUN pip install poetry
COPY ../pyproject.toml ../poetry.lock ../README.md ./

RUN poetry install --no-root --with core,web

ENV PYTHONPATH="${PYTHONPATH}:/myapp/web/app:/myapp/core/app"

ENTRYPOINT ["pytest", "--basetemp=/tmp/pytest", "-s", "tests"]
