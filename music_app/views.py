import re
import requests
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.conf import settings
from .models import SavedTrack, Playlist, PlaylistTrack

YANDEX_TOKEN = getattr(settings, 'YANDEX_MUSIC_TOKEN', 'y0__wgBEIax8ZQEGN74BiDM5d2yFwfk4z3DCxsQ_J3ydRLNLFoQC7-Z')
GENIUS_TOKEN = getattr(settings, 'GENIUS_ACCESS_TOKEN', '9eQRF8FyUyGC-HloK7JTq-LgmKOJG94Eu7b2YVfMSMFHups-Ma_-RIcPg55usosC')


def get_ya_client():
    try:
        from yandex_music import Client
        if YANDEX_TOKEN:
            return Client(YANDEX_TOKEN).init()
    except:
        pass
    return None


@login_required
def music_player(request):
    saved_tracks = SavedTrack.objects.filter(user=request.user).order_by('-created_at')[:50]
    return render(request, 'music_app/player.html', {
        'saved_tracks': saved_tracks,
        'saved_count': SavedTrack.objects.filter(user=request.user).count(),
        'playlists': Playlist.objects.filter(user=request.user).prefetch_related('tracks'),
    })


@login_required
def search_music(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'tracks': []})

    tracks = []
    client = get_ya_client()
    if client:
        try:
            result = client.search(query)
            items = []
            if hasattr(result, 'tracks') and result.tracks:
                items = result.tracks.results if hasattr(result.tracks, 'results') else result.tracks

            for track in items[:30]:
                cover = ''
                if hasattr(track, 'cover_uri') and track.cover_uri:
                    cover = f'https://{track.cover_uri.replace("%%", "400x400")}'
                artist = ', '.join(a.name for a in track.artists) if track.artists else ''
                tracks.append({
                    'id': str(track.id),
                    'title': track.title,
                    'artist': artist or 'Неизвестен',
                    'cover_url': cover,
                    'duration': track.duration_ms // 1000 if hasattr(track, 'duration_ms') else 0,
                })
        except Exception as e:
            print(f'Search error: {e}')
    return JsonResponse({'tracks': tracks})

@login_required
def my_wave(request):
    """Моя волна — каждый раз новые треки через ротор"""
    tracks = []
    seen_ids = set()
    client = get_ya_client()
    if not client:
        return JsonResponse({'tracks': []})

    # Пробуем ротор 3 раза
    for attempt in range(3):
        try:
            rotor = client.rotor_station_tracks('user:onyourwave')
            for track_item in rotor.sequence:
                t = track_item.track
                tid = str(t.id)
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)
                cover = f'https://{t.cover_uri.replace("%%", "400x400")}' if hasattr(t, 'cover_uri') and t.cover_uri else ''
                artist = ', '.join(a.name for a in t.artists) if hasattr(t, 'artists') and t.artists else ''
                tracks.append({
                    'id': tid, 'title': t.title, 'artist': artist or 'Неизвестен',
                    'cover_url': cover, 'duration': t.duration_ms // 1000 if hasattr(t, 'duration_ms') else 0,
                })
            if len(tracks) >= 30:
                break
        except Exception as e:
            print(f'Rotor attempt {attempt}: {e}')
            continue

    # Fallback: чарт
    if len(tracks) < 10:
        try:
            chart = client.chart()
            items = chart.chart.tracks if hasattr(chart.chart, 'tracks') else chart.chart.tracks
            for item in items:
                t = item.track if hasattr(item, 'track') else item
                tid = str(t.id)
                if tid in seen_ids: continue
                seen_ids.add(tid)
                cover = f'https://{t.cover_uri.replace("%%", "400x400")}' if hasattr(t, 'cover_uri') and t.cover_uri else ''
                artist = ', '.join(a.name for a in t.artists) if hasattr(t, 'artists') and t.artists else ''
                tracks.append({
                    'id': tid, 'title': t.title, 'artist': artist or 'Неизвестен',
                    'cover_url': cover, 'duration': t.duration_ms // 1000 if hasattr(t, 'duration_ms') else 0,
                })
        except:
            pass

    return JsonResponse({'tracks': tracks})

@login_required
def get_audio_url(request):
    track_id = request.GET.get('track_id', '')
    if not track_id:
        return JsonResponse({'url': ''})
    client = get_ya_client()
    if client:
        try:
            track_full = client.tracks([track_id])[0]
            info = track_full.get_download_info(get_direct_links=True)
            if info:
                best = max(info, key=lambda x: x.bitrate_in_kbps if hasattr(x, 'bitrate_in_kbps') and x.bitrate_in_kbps else 0)
                url = best.get_direct_link()
                if url:
                    return JsonResponse({'url': url})
        except Exception as e:
            print(f'Audio URL error: {e}')
    return JsonResponse({'url': ''})


@login_required
def get_lyrics(request):
    """Текст песни через Genius API"""
    artist = request.GET.get('artist', '').strip()
    title = request.GET.get('title', '').strip()

    # Чистим название: убираем (feat. XXX), [Remix] и т.д.
    title_clean = re.sub(r'\s*\(.*?\)', '', title)
    title_clean = re.sub(r'\s*\[.*?\]', '', title_clean)
    # Берём только основного артиста
    artist_clean = artist.split(',')[0].strip()

    lyrics = 'Текст не найден'

    try:
        # Поиск на Genius
        headers = {'Authorization': f'Bearer {GENIUS_TOKEN}'}
        params = {'q': f'{artist_clean} - {title_clean}'}

        r = requests.get('https://api.genius.com/search', params=params, headers=headers, timeout=10)
        data = r.json()

        if data.get('response', {}).get('hits'):
            # Ищем точное совпадение по артисту
            best_hit = None
            for hit in data['response']['hits']:
                result = hit['result']
                if artist_clean.lower() in result['primary_artist']['name'].lower():
                    best_hit = result
                    break
            if not best_hit:
                best_hit = data['response']['hits'][0]['result']

            song_url = best_hit['url']

            # Парсим страницу
            page = requests.get(song_url,
                                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                                timeout=15)

            # Ищем текст разными способами
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(page.text, 'html.parser')

            # Способ 1: data-lyrics-container
            lyrics_divs = soup.find_all('div', {'data-lyrics-container': 'true'})
            if lyrics_divs:
                parts = []
                for div in lyrics_divs:
                    html = str(div).replace('<br/>', '\n').replace('<br>', '\n')
                    html = re.sub(r'<[^>]+>', '', html)
                    html = html.strip()
                    if html:
                        parts.append(html)
                lyrics = '\n\n'.join(parts)

            # Способ 2: класс lyrics
            if lyrics == 'Текст не найден':
                lyrics_div = soup.find('div', class_='lyrics')
                if lyrics_div:
                    lyrics = lyrics_div.get_text('\n').strip()

            # Способ 3: все <p> теги
            if lyrics == 'Текст не найден':
                p_tags = soup.find_all('p')
                long_ps = [p.get_text().strip() for p in p_tags if len(p.get_text().strip()) > 30]
                if long_ps:
                    lyrics = '\n\n'.join(long_ps)

            # Чистим
            lyrics = lyrics.replace('You might also like', '')
            lyrics = re.sub(r'\n{3,}', '\n\n', lyrics)
            lyrics = lyrics.strip()

            if not lyrics or len(lyrics) < 10:
                lyrics = 'Текст не найден'

    except Exception as e:
        print(f'Lyrics error: {e}')

    return JsonResponse({'lyrics': lyrics})


@login_required
@require_POST
def save_track(request):
    track_id = request.POST.get('track_id', '')
    title = request.POST.get('title', '')
    artist = request.POST.get('artist', '')
    cover_url = request.POST.get('cover_url', '')
    duration = request.POST.get('duration', 0)
    if not track_id:
        return JsonResponse({'success': False}, status=400)
    track, created = SavedTrack.objects.get_or_create(
        user=request.user, track_id=track_id,
        defaults={'title': title, 'artist': artist, 'cover_url': cover_url,
                  'duration': int(duration) if duration else 0})
    return JsonResponse({'success': True, 'created': created})


@login_required
@require_POST
def remove_track(request):
    track_id = request.POST.get('track_id', '')
    SavedTrack.objects.filter(user=request.user, track_id=track_id).delete()
    return JsonResponse({'success': True})


@login_required
def playlist_list(request):
    names = list(Playlist.objects.filter(user=request.user).values_list('name', flat=True))
    return JsonResponse({'names': names})


@login_required
@require_POST
def playlist_create(request):
    name = request.POST.get('name', '').strip()
    cover = request.FILES.get('cover')  # ← ВАЖНО: request.FILES
    if not name:
        return JsonResponse({'success': False}, status=400)
    pl, created = Playlist.objects.get_or_create(user=request.user, name=name)
    if cover:
        pl.cover = cover
        pl.save()
    return JsonResponse({'success': True, 'created': created, 'name': pl.name, 'cover_url': pl.cover.url if pl.cover else ''})


@login_required
@require_POST
def playlist_delete(request):
    name = request.POST.get('name', '')
    Playlist.objects.filter(user=request.user, name=name).delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def playlist_add_track(request):
    name = request.POST.get('name', '')
    track_id = request.POST.get('track_id', '')
    title = request.POST.get('title', '')
    artist = request.POST.get('artist', '')
    cover_url = request.POST.get('cover_url', '')
    pl = Playlist.objects.filter(user=request.user, name=name).first()
    if not pl:
        return JsonResponse({'success': False}, status=400)
    pt, created = PlaylistTrack.objects.get_or_create(
        playlist=pl, track_id=track_id,
        defaults={'title': title, 'artist': artist, 'cover_url': cover_url})
    return JsonResponse({'success': True, 'created': created})


@login_required
def playlist_tracks(request):
    name = request.GET.get('name', '')
    pl = Playlist.objects.filter(user=request.user, name=name).first()
    if not pl:
        return JsonResponse({'tracks': []})
    tracks = [{'id': t.track_id, 'title': t.title, 'artist': t.artist, 'cover_url': t.cover_url}
              for t in pl.tracks.all()]
    return JsonResponse({
        'tracks': tracks,
        'cover_url': pl.cover.url if pl.cover else '',
        'name': pl.name
    })

@login_required
@require_POST
def playlist_remove_track(request):
    name = request.POST.get('name', '')
    track_id = request.POST.get('track_id', '')
    pl = Playlist.objects.filter(user=request.user, name=name).first()
    if pl:
        PlaylistTrack.objects.filter(playlist=pl, track_id=track_id).delete()
    return JsonResponse({'success': True})