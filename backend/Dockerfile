FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# Ship the Alembic config + migrations so schema migrations can be run as a
# one-off ECS task against the (private) Aurora cluster — see docs/DEPLOYMENT.md.
COPY alembic.ini .
COPY migrations ./migrations

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
