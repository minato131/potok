# 🌊 Potok - Социальная платформа

[![Django](https://img.shields.io/badge/Django-4.x-092E20?style=flat-square&logo=django)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

**Potok** — это социальная платформа для микроблогов с возможностью создания постов, обмена сообщениями и общения в сообществах.

---

## 📋 Содержание
- [Возможности](#-возможности)
- [Установка](#-установка)
- [Структура](#-структура)
- [Команды](#-команды)
- [Устранение проблем](#-устранение-проблем)

---

## ✨ Возможности

### 👥 Пользователи
- Регистрация и профили с аватарами
- Подписки на других пользователей
- Личная лента постов

### 📝 Посты
- Создание записей с текстом и фото
- Лайки и комментарии
- Репосты записей

### 💬 Общение
- Личные сообщения (мессенджер)
- Тематические сообщества
- Система уведомлений

### 🛡️ Модерация
- Жалобы на контент
- Блокировка пользователей
- Логи действий

---

## 🚀 Установка

### Требования
- Python 3.10+
- Git

### Быстрый старт

```bash
# 1. Клонируем репозиторий
git clone https://github.com/minato131/potok.git
cd potok

# 2. Создаем виртуальное окружение
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 3. Устанавливаем зависимости
pip install -r requirements.txt

# 4. Настраиваем БД
python manage.py migrate

# 5. Создаем админа
python manage.py createsuperuser

# 6. Запускаем сервер
python manage.py runserver
После установки откройте http://127.0.0.1:8000

📁 Структура
text
potok/
├── manage.py
├── requirements.txt
├── potok/              # Настройки проекта
├── accounts/           # Пользователи
├── posts/              # Посты и лента
├── communities/        # Сообщества
├── messenger/          # Личные сообщения
├── moderation/         # Модерация
├── templates/          # Шаблоны
├── static/             # CSS, JS
└── media/              # Загрузки
🎯 Основные маршруты
URL	Описание
/	Главная лента
/admin/	Админка
/accounts/register/	Регистрация
/accounts/login/	Вход
/profile/username/	Профиль
/posts/create/	Создать пост
/communities/	Сообщества
/messenger/	Сообщения
🛠️ Полезные команды
bash
# Создание миграций
python manage.py makemigrations

# Применение миграций
python manage.py migrate

# Сбор статики
python manage.py collectstatic

# Запуск тестов
python manage.py test

# Создание админа
python manage.py createsuperuser
🔧 Возможные проблемы
<details> <summary><b>Ошибка "No module named ..."</b></summary>
text
# Активируйте виртуальное окружение и переустановите пакеты
pip install -r requirements.txt --force-reinstall
</details><details> <summary><b>Ошибки базы данных</b></summary>
text
# Сброс БД
rm -f db.sqlite3  # или del db.sqlite3 для Windows
python manage.py migrate
</details><details> <summary><b>Порт 8000 занят</b></summary>
text
# Используйте другой порт
python manage.py runserver 8080
</details>
🤝 Участие в проекте
Форкните репозиторий

Создайте ветку (git checkout -b feature/name)

Закоммитьте изменения (git commit -m 'Add feature')

Отправьте ветку (git push origin feature/name)

Откройте Pull Request

📄 Лицензия
MIT © minato131
