import uuid
import requests
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from posts.models import Post
from .models import SavedPhoto, SavedVideo
from django.views.decorators.csrf import csrf_exempt
import json

# media_storage/views.py
@login_required
def photo_list(request):
    photos = SavedPhoto.objects.filter(user=request.user).select_related('post').order_by('-created_at')

    total_count = photos.count()
    saved_count = photos.filter(post__isnull=False).count()
    uploaded_count = photos.filter(post__isnull=True).count()

    paginator = Paginator(photos, 24)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)

    return render(request, 'media_storage/photo_list.html', {
        'photos': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'page_obj': page_obj,
        'total_count': total_count,
        'saved_count': saved_count,
        'uploaded_count': uploaded_count,
    })


@login_required
def video_list(request):
    videos = SavedVideo.objects.filter(user=request.user).select_related('post').order_by('-created_at')

    # Счётчики для фильтров
    total_count = videos.count()
    saved_count = videos.filter(post__isnull=False).count()
    uploaded_count = videos.filter(post__isnull=True).count()

    paginator = Paginator(videos, 24)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)

    return render(request, 'media_storage/video_list.html', {
        'videos': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'page_obj': page_obj,
        'total_count': total_count,
        'saved_count': saved_count,
        'uploaded_count': uploaded_count,
    })



@login_required
@require_POST
def photo_delete(request, photo_id):
    """Удалить фото"""
    photo = get_object_or_404(SavedPhoto, id=photo_id, user=request.user)
    photo.image.delete()
    photo.delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def video_delete(request, video_id):
    """Удалить видео"""
    video = get_object_or_404(SavedVideo, id=video_id, user=request.user)
    video.file.delete()
    video.delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def save_media_from_post(request):
    post_id = request.POST.get('post_id')
    media_type = request.POST.get('media_type')

    post = get_object_or_404(Post, id=post_id)

    if media_type == 'photo' and post.image:
        existing = SavedPhoto.objects.filter(user=request.user, post=post).first()
        if existing:
            return JsonResponse({'success': False, 'already_exists': True, 'error': 'Фото уже сохранено'})

        photo = SavedPhoto.objects.create(user=request.user, post=post)
        photo.image.save(post.image.name, post.image.file, save=True)
        return JsonResponse({'success': True})

    elif media_type == 'video' and post.video:
        existing = SavedVideo.objects.filter(user=request.user, post=post).first()
        if existing:
            return JsonResponse({'success': False, 'already_exists': True, 'error': 'Видео уже сохранено'})

        video = SavedVideo.objects.create(user=request.user, post=post)
        video.file.save(post.video.name, post.video.file, save=True)
        return JsonResponse({'success': True})

    return JsonResponse({'success': False, 'error': 'Нет медиа'})


# ========== НОВАЯ ФУНКЦИЯ ДЛЯ СОХРАНЕНИЯ ПО URL (С ВЫБОРОМ) ==========
@login_required
@csrf_exempt
def save_media_from_url(request):
    """Сохранить медиа из URL (для выбора конкретного фото/видео из поста)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        media_url = data.get('url')
        media_type = data.get('media_type')  # 'image' или 'video'
        post_id = data.get('post_id')

        if not media_url:
            return JsonResponse({'success': False, 'error': 'URL не указан'}, status=400)

        # ПРЕОБРАЗУЕМ ОТНОСИТЕЛЬНЫЙ URL В АБСОЛЮТНЫЙ
        if media_url.startswith('/'):
            from django.conf import settings
            # Получаем домен из настроек или из запроса
            from django.contrib.sites.shortcuts import get_current_site
            from urllib.parse import urljoin

            # Пытаемся получить домен из запроса (через request не передаётся, нужно добавить)
            # Временное решение — используем относительный путь, requests не поймёт
            # Поэтому нужно получить полный URL
            domain = settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'http://127.0.0.1:8000'
            media_url = urljoin(domain, media_url)

        # Проверяем, не сохранял ли пользователь уже этот URL
        if media_type == 'image':
            existing = SavedPhoto.objects.filter(
                user=request.user,
                original_url=media_url
            ).first()
        else:
            existing = SavedVideo.objects.filter(
                user=request.user,
                original_url=media_url
            ).first()

        if existing:
            return JsonResponse({'success': False, 'already_exists': True})

        # Скачиваем файл по URL
        try:
            response = requests.get(media_url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()

            # Определяем расширение и имя файла
            content_type = response.headers.get('content-type', '')
            filename = f"{uuid.uuid4().hex}"

            if media_type == 'image':
                if 'png' in content_type:
                    filename += '.png'
                elif 'gif' in content_type:
                    filename += '.gif'
                elif 'webp' in content_type:
                    filename += '.webp'
                else:
                    filename += '.jpg'

                photo = SavedPhoto.objects.create(
                    user=request.user,
                    original_url=media_url,
                    source_post_id=post_id
                )
                photo.image.save(filename, ContentFile(response.content), save=True)
                return JsonResponse({'success': True, 'media_id': photo.id})

            else:  # video
                if 'webm' in content_type:
                    filename += '.webm'
                else:
                    filename += '.mp4'

                video = SavedVideo.objects.create(
                    user=request.user,
                    original_url=media_url,
                    source_post_id=post_id
                )
                video.file.save(filename, ContentFile(response.content), save=True)
                return JsonResponse({'success': True, 'media_id': video.id})

        except requests.exceptions.RequestException as e:
            return JsonResponse({'success': False, 'error': f'Ошибка загрузки: {str(e)}'}, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Неверный формат данных'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def upload_photo(request):
    """Загрузить фото с устройства"""
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'success': False, 'error': 'Файл не выбран'}, status=400)

    if not file.content_type.startswith('image/'):
        return JsonResponse({'success': False, 'error': 'Только изображения'}, status=400)

    photo = SavedPhoto.objects.create(user=request.user)
    photo.image.save(file.name, file)
    return JsonResponse({'success': True, 'id': photo.id, 'url': photo.image.url})


@login_required
@require_POST
def upload_video(request):
    """Загрузить видео с устройства"""
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'success': False, 'error': 'Файл не выбран'}, status=400)

    if not file.content_type.startswith('video/'):
        return JsonResponse({'success': False, 'error': 'Только видео'}, status=400)

    video = SavedVideo.objects.create(user=request.user)
    video.file.save(file.name, file)
    return JsonResponse({'success': True, 'id': video.id, 'url': video.file.url})


@login_required
@require_POST
def delete_selected_photos(request):
    """Удалить несколько выбранных фото"""
    photo_ids = request.POST.getlist('photo_ids[]')
    if not photo_ids:
        return JsonResponse({'success': False, 'error': 'Не выбраны фото'}, status=400)

    photos = SavedPhoto.objects.filter(id__in=photo_ids, user=request.user)
    deleted_count = 0
    for photo in photos:
        photo.image.delete()
        photo.delete()
        deleted_count += 1

    return JsonResponse({'success': True, 'deleted_count': deleted_count})


@login_required
@require_POST
def delete_selected_videos(request):
    """Удалить несколько выбранных видео"""
    video_ids = request.POST.getlist('video_ids[]')
    if not video_ids:
        return JsonResponse({'success': False, 'error': 'Не выбраны видео'}, status=400)

    videos = SavedVideo.objects.filter(id__in=video_ids, user=request.user)
    deleted_count = 0
    for video in videos:
        video.file.delete()
        video.delete()
        deleted_count += 1

    return JsonResponse({'success': True, 'deleted_count': deleted_count})