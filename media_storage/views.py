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
        # Проверяем, не сохранял ли пользователь уже это фото
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