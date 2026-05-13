import os
import random
import django
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils.text import slugify

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'potok.settings')
django.setup()

User = get_user_model()
from posts.models import Post, Comment, Like, Category, Tag, Bookmark, PostView
from accounts.models import Profile, Follow, Friendship
from communities.models import Community, CommunityPost, CommunityMembership
from media_storage.models import SavedPhoto, SavedVideo

print("🚀 Генерация тестовых данных...")

# ===== 1. ПОЛЬЗОВАТЕЛИ =====
usernames = [
    'tech_guru', 'music_lover', 'art_master', 'code_ninja', 'book_worm',
    'photo_hunter', 'travel_bug', 'food_critic', 'sport_fan', 'movie_buff',
    'science_geek', 'history_nerd', 'fashion_icon', 'car_enthusiast', 'pet_lover',
    'garden_wizard', 'yoga_master', 'game_player', 'dance_queen', 'design_pro',
    'alex_smith', 'maria_rose', 'dmitry_frost', 'elena_star', 'ivan_wolf',
    'olga_night', 'pavel_fire', 'anna_sky', 'sergey_rock', 'katya_rain',
]

users = []
for i, username in enumerate(usernames):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            'email': f'{username}@example.com',
            'first_name': username.split('_')[0].title(),
            'last_name': username.split('_')[1].title() if '_' in username else 'User',
            'password': 'pbkdf2_sha256$...',
        }
    )
    if created:
        user.set_password('testpass123')
        user.save()
        Profile.objects.filter(user=user).update(
            bio=f'Привет! Я {user.first_name}. {random.choice(["Люблю программировать", "Обожаю музыку", "Путешествую по миру", "Фотографирую природу", "Читаю книги", "Занимаюсь спортом"])}',
            location=random.choice(['Москва', 'СПб', 'Казань', 'Новосибирск', 'Екатеринбург', 'Калининград', 'Сочи']),
            website=f'https://{username}.example.com' if random.random() > 0.5 else '',
        )
    users.append(user)
    print(f"  👤 {username}")

# ===== 2. КАТЕГОРИИ =====
categories_data = [
    ('Технологии', 'Всё о технологиях и инновациях'),
    ('Музыка', 'Обсуждение музыки и артистов'),
    ('Искусство', 'Картины, скульптура, дизайн'),
    ('Программирование', 'Код, алгоритмы, архитектура'),
    ('Книги', 'Рецензии и обсуждения книг'),
    ('Фотография', 'Советы по фотосъёмке'),
    ('Путешествия', 'Отчёты о путешествиях'),
    ('Еда', 'Рецепты и обзоры ресторанов'),
    ('Спорт', 'Фитнес, футбол, баскетбол'),
    ('Кино', 'Фильмы, сериалы, анимация'),
]

categories = []
for name, desc in categories_data:
    cat_slug = slugify(name)
    if not cat_slug:
        cat_slug = f'cat-{random.randint(10000,99999)}'
    cat, _ = Category.objects.get_or_create(
        name=name,
        defaults={'slug': cat_slug, 'description': desc}
    )
    categories.append(cat)

# ===== 3. ТЕГИ =====
tag_names = [
    'python', 'django', 'javascript', 'react', 'tutorial', 'news', 'review',
    'photo', 'video', 'music', 'rock', 'pop', 'jazz', 'classic', 'hiphop',
    'design', 'ui', 'ux', 'api', 'database', 'docker', 'linux', 'ai', 'ml',
    'travel', 'food', 'fitness', 'health', 'nature', 'city', 'sunset',
    'retro', 'vintage', 'modern', 'abstract', 'portrait', 'landscape',
]

tags = []
for name in tag_names:
    tag_slug = slugify(name)
    if not tag_slug:
        tag_slug = f'tag-{random.randint(10000,99999)}'
    tag, _ = Tag.objects.get_or_create(
        name=name,
        defaults={'slug': tag_slug}
    )
    tags.append(tag)

# ===== 4. СООБЩЕСТВА =====
community_data = [
    ('python_dev', 'Python разработчики'),
    ('js_world', 'JavaScript сообщество'),
    ('rock_fans', 'Фанаты рока'),
    ('photo_club', 'Клуб фотографов'),
    ('travel_community', 'Путешественники'),
    ('food_lovers', 'Любители еды'),
    ('fitness_gang', 'Фитнес группа'),
    ('movie_club', 'Киноманы'),
    ('art_studio', 'Арт студия'),
    ('book_club', 'Книжный клуб'),
]

communities = []
for slug, name in community_data:
    comm, _ = Community.objects.get_or_create(
        slug=slug,
        defaults={'name': name, 'description': f'Сообщество {name}', 'status': 'active'}
    )
    communities.append(comm)

# ===== 5. ПОДПИСКИ И ДРУЗЬЯ =====
print("🔗 Создание связей...")
for user in users:
    # Подписки
    following = random.sample([u for u in users if u != user], random.randint(3, 10))
    for target in following:
        Follow.objects.get_or_create(follower=user, following=target)

    # Друзья
    friends = random.sample([u for u in users if u != user], random.randint(2, 8))
    for friend in friends:
        Friendship.objects.get_or_create(user=user, friend=friend)

    # Вступление в сообщества
    user_comms = random.sample(communities, random.randint(2, 6))
    for comm in user_comms:
        CommunityMembership.objects.get_or_create(user=user, community=comm, defaults={'status': 'active'})

# ===== 6. ПОСТЫ =====
print("📝 Создание постов...")
post_templates = [
    "Делюсь своими мыслями о {topic}. Это невероятно интересная тема, которую стоит обсудить!",
    "Только что закончил работу над проектом по {topic}. Получилось круто!",
    "Обзор нового {topic}. Впечатления просто потрясающие, рекомендую всем.",
    "Как я изучал {topic} в течение года. Мой опыт и советы новичкам.",
    "Топ-10 причин заняться {topic} прямо сейчас. Не откладывайте!",
    "Сравнение популярных инструментов для {topic}. Что выбрать в 2025 году?",
    "Моя история успеха в {topic}. От новичка до профессионала за 6 месяцев.",
    "Почему я люблю {topic} и вам советую. Личный опыт и рекомендации.",
    "Глубокий анализ {topic}. Цифры, факты и неожиданные выводы.",
    "Будущее {topic}: тренды, прогнозы и мои ожидания.",
]

posts = []
for _ in range(100):
    user = random.choice(users)
    category = random.choice(categories)
    topic = category.name.lower()
    title_templates = [
        f"Мой опыт в {topic}",
        f"Обзор {topic}: что нужно знать",
        f"Как начать в {topic}",
        f"{topic.title()} для начинающих",
        f"Продвинутый {topic}",
        f"Секреты {topic}",
        f"{topic.title()}: полное руководство",
        f"Почему {topic} важен",
        f"Тренды {topic} в 2025",
        f"Мой путь в {topic}",
    ]

    post = Post.objects.create(
        author=user,
        title=random.choice(title_templates),
        content=random.choice(post_templates).format(topic=topic),
        category=category,
        status='published',
        likes_count=random.randint(0, 50),
        views_count=random.randint(10, 500),
        comments_count=0,
        created_at=timezone.now() - timedelta(days=random.randint(0, 365)),
    )

    # Теги
    post_tags = random.sample(tags, random.randint(2, 5))
    post.tags.set(post_tags)
    posts.append(post)

    # Привязка к сообществу (30% шанс)
    if random.random() < 0.3:
        community = random.choice(communities)
        CommunityPost.objects.get_or_create(post=post, community=community)

print(f"  ✅ {len(posts)} постов создано")

# ===== 7. КОММЕНТАРИИ =====
print("💬 Создание комментариев...")
comment_texts = [
    "Отличный пост! Очень познавательно.",
    "Спасибо за информацию, было интересно.",
    "Я тоже так думаю, полностью согласен.",
    "Можете рассказать подробнее?",
    "Это просто невероятно! Продолжайте в том же духе.",
    "У меня был похожий опыт, могу подтвердить.",
    "Отличная работа, жду новых постов!",
    "Не совсем согласен, но интересная точка зрения.",
    "Где можно узнать больше об этом?",
    "Потрясающе! Сохранил в закладки.",
    "Очень полезно, спасибо!",
    "Давно искал такую информацию.",
    "Круто! А есть ещё примеры?",
    "Поддерживаю, тема важная.",
    "Интересно, не знал об этом.",
]

comment_count = 0
for post in random.sample(posts, 80):
    num_comments = random.randint(1, 8)
    for _ in range(num_comments):
        comment = Comment.objects.create(
            author=random.choice(users),
            post=post,
            content=random.choice(comment_texts),
            is_approved=True,
            is_deleted=False,
            created_at=timezone.now() - timedelta(days=random.randint(0, 300)),
        )
        comment_count += 1

    post.comments_count = post.comments.filter(is_deleted=False).count()
    post.save(update_fields=['comments_count'])

print(f"  ✅ {comment_count} комментариев создано")

# ===== 8. ЛАЙКИ =====
print("❤️ Создание лайков...")
like_count = 0
for post in random.sample(posts, 90):
    likers = random.sample(users, random.randint(3, 20))
    for user in likers:
        Like.objects.get_or_create(
            user=user,
            content_type='post',
            object_id=post.id,
            defaults={'like_type': random.choice(['like', 'love'])}
        )
        like_count += 1

    post.likes_count = Like.objects.filter(content_type='post', object_id=post.id).count()
    post.save(update_fields=['likes_count'])

print(f"  ✅ {like_count} лайков создано")

# ===== 9. ЗАКЛАДКИ =====
print("🔖 Создание закладок...")
bookmark_count = 0
for post in random.sample(posts, 70):
    savers = random.sample(users, random.randint(1, 6))
    for user in savers:
        Bookmark.objects.get_or_create(user=user, post=post)
        bookmark_count += 1

print(f"  ✅ {bookmark_count} закладок создано")

# ===== 10. ПРОСМОТРЫ =====
print("👁 Создание просмотров...")
view_count = 0
for post in random.sample(posts, 60):
    viewers = random.sample(users, random.randint(5, 30))
    for user in viewers:
        PostView.objects.get_or_create(
            post=post,
            user=user,
            defaults={'viewed_at': timezone.now() - timedelta(hours=random.randint(1, 720))}
        )
        view_count += 1

print(f"  ✅ {view_count} просмотров создано")

print("\n🎉 Готово! Тестовые данные созданы.")
print(f"   Пользователей: {len(users)}")
print(f"   Постов: {len(posts)}")
print(f"   Комментариев: {comment_count}")
print(f"   Лайков: {like_count}")
print(f"   Закладок: {bookmark_count}")
print(f"   Сообществ: {len(communities)}")
print(f"   Категорий: {len(categories)}")
print(f"   Тегов: {len(tags)}")
print("\n🔑 Пароль для всех: testpass123")