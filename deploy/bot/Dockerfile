FROM python:3.13-slim

ARG BACKET_INSTALL_SPEC=""

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BACKET_SKIP_UPDATE_CHECK=1

WORKDIR /app

RUN python -m pip install --upgrade pip \
    && if [ -n "${BACKET_INSTALL_SPEC}" ]; then \
         printf '%s\n' "${BACKET_INSTALL_SPEC}" > /tmp/backet-requirements.txt; \
       else \
         printf '%s\n' 'backet[bot] @ https://github.com/jsvitkin/backet/releases/download/v0.1.23/backet-0.1.23-py3-none-any.whl' > /tmp/backet-requirements.txt; \
       fi \
    && python -m pip install -r /tmp/backet-requirements.txt \
    && rm /tmp/backet-requirements.txt

RUN useradd --create-home --uid 10001 backet
USER backet

ENTRYPOINT ["backet"]
CMD ["bot", "run", "/srv/backet-bot/data/current"]
