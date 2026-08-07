FROM python:3.12-slim AS builder

ENV POETRY_VERSION=2.4.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-ansi


FROM python:3.12-slim AS runtime

ARG APP_VERSION=0.1.0
ARG RENDER_GIT_COMMIT=development
ARG GIT_SHA=${RENDER_GIT_COMMIT}

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION="${APP_VERSION}" \
    GIT_SHA="${GIT_SHA}"

LABEL org.opencontainers.image.title="Alpha Engine" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}"

RUN groupadd --gid 10001 alpha \
    && useradd --uid 10001 --gid alpha --create-home alpha

WORKDIR /app

COPY --from=builder --chown=alpha:alpha /app/.venv /app/.venv
COPY --chown=alpha:alpha app /app/app
COPY --chown=alpha:alpha migrations /app/migrations
COPY --chown=alpha:alpha alembic.ini /app/alembic.ini

USER alpha

EXPOSE 8000

CMD ["uvicorn", "app.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
