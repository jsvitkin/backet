FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BACKET_SKIP_UPDATE_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY metadata /app/metadata

RUN python -m pip install --upgrade pip \
    && python -m pip install '.[bot]'

RUN useradd --create-home --uid 10001 backet
USER backet

ENTRYPOINT ["backet"]
CMD ["bot", "run", "/srv/backet-bot/data/current"]
