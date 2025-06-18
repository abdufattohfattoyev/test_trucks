FROM python:3.11-slim

WORKDIR /app

# Tizim bog‘liqliklarini o‘rnatish
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python bog‘liqliklarini o‘rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Loyiha fayllarini nusxalash
COPY . .

# Statik fayllarni yig‘ish
RUN python manage.py collectstatic --noinput

# Portni ochish
EXPOSE 8002

# Django-ni ishga tushirish
CMD ["gunicorn", "--bind", "0.0.0.0:8002", "config.wsgi:application"]