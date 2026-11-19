# Серверная часть системы обзоров и пользовательских оценок игр

Стек: Python 3.12, FastAPI, PostgreSQL 16 (SQLAlchemy 2.x + asyncpg), Redis, RabbitMQ, Docker Compose.

## Быстрый запуск
docker compose up --build

Swagger UI: http://localhost:8000/docs  
RabbitMQ UI: http://localhost:15672 (guest / guest)

## Запуск тестов и линтеров
pytest
flake8 src tests --max-line-length=100
black --check src tests