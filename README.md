# Социальная сеть "Поток"

Веб-приложение для создания и распространения пользовательского контента, объединения в тематические сообщества и обмена личными сообщениями.

## Технологии

- Python 3.12
- Django 4.2
- PostgreSQL 16
- Docker / Docker Compose

## Настройка окружения

Создайте файл `.env` в корне проекта на основе `example.env`:

```env
# Django settings
DEBUG=True
SECRET_KEY=your-secret-key-here
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database settings
DB_NAME=db_potok
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=db
DB_PORT=5432

# Email settings (для отправки писем)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=tinton220221@gmail.com


//Запуск через Docker
Клонируйте репозиторий:
 git clone https://github.com/your-username/potok.git
 cd potok
Создайте файл .env (см. example.env)

//Запустите контейнеры:

 docker-compose up -d --build
Приложение доступно по адресу: http://localhost:8000

//Создайте суперпользователя:

 docker-compose exec web python manage.py createsuperuser

//Локальный запуск (без Docker)
 Установите PostgreSQL и создайте базу данных

//Создайте виртуальное окружение:

 python -m venv venv
 source venv/bin/activate  # Linux/Mac
 venv\Scripts\activate     # Windows

//Установите зависимости:

 pip install -r requirements.txt

//Примените миграции:

 python manage.py migrate

//Запустите сервер:

 python manage.py runserver