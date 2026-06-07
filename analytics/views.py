from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q, F, Sum
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
import json
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from posts.models import Post, Comment, Like, Category, Tag
from accounts.models import User
from communities.models import Community
from moderation.models import Report, Ban
from accounts.models import User
from posts.models import Post, Comment, Like, PostView
from communities.models import Community
from moderation.models import Report, Ban
import os
from datetime import datetime
from io import BytesIO
from django.conf import settings
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

@staff_member_required
def dashboard(request):
    """Дашборд аналитики (только для администраторов)"""
    return render(request, 'analytics/dashboard.html')


@staff_member_required
def data(request):
    """API для получения данных для графиков"""
    days = int(request.GET.get('days', 30))
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    # Данные по дням
    dates = []
    users_data = []
    posts_data = []
    comments_data = []
    likes_data = []
    reports_data = []

    current = start_date
    while current <= end_date:
        date_str = current.strftime('%d.%m')

        users_count = User.objects.filter(date_joined__date=current.date()).count()
        posts_count = Post.objects.filter(created_at__date=current.date()).count()
        comments_count = Comment.objects.filter(created_at__date=current.date()).count()
        likes_count = Like.objects.filter(created_at__date=current.date()).count()
        reports_count = Report.objects.filter(created_at__date=current.date()).count()

        dates.append(date_str)
        users_data.append(users_count)
        posts_data.append(posts_count)
        comments_data.append(comments_count)
        likes_data.append(likes_count)
        reports_data.append(reports_count)

        current += timedelta(days=1)

    # Топ пользователей
    top_users = User.objects.annotate(
        posts_count=Count('posts', filter=Q(posts__status='published')),
        comments_count=Count('comments', filter=Q(comments__is_deleted=False)),
        total_activity=Count('posts') + Count('comments') * 2
    ).order_by('-total_activity')[:10].values('id', 'username', 'posts_count', 'comments_count')

    # Топ постов
    top_posts = Post.objects.filter(status='published').annotate(
        total_score=F('likes_count') * 2 + F('comments_count') * 3 + F('views_count')
    ).order_by('-total_score')[:10].values('id', 'title', 'likes_count', 'comments_count', 'views_count')

    # Общая статистика
    total_stats = {
        'users': User.objects.count(),
        'posts': Post.objects.filter(status='published').count(),
        'comments': Comment.objects.filter(is_deleted=False).count(),
        'likes': Like.objects.count(),
        'communities': Community.objects.filter(status='active').count(),
        'reports': Report.objects.filter(status='pending').count(),
        'bans': Ban.objects.filter(lifted_at__isnull=True).count(),
    }

    return JsonResponse({
        'dates': dates,
        'users_data': users_data,
        'posts_data': posts_data,
        'comments_data': comments_data,
        'likes_data': likes_data,
        'reports_data': reports_data,
        'top_users': list(top_users),
        'top_posts': list(top_posts),
        'total_stats': total_stats,
    })


@staff_member_required
def export_pdf(request):
    """Экспорт аналитики в PDF с фильтрами и метаданными"""

    # ===== ПОЛУЧАЕМ ПАРАМЕТРЫ ФИЛЬТРАЦИИ =====
    days = int(request.GET.get('days', 30))
    export_type = request.GET.get('type', 'full')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    now = timezone.now()

    # Обработка кастомных дат
    if date_from and date_to:
        try:
            start_date = datetime.strptime(date_from, '%Y-%m-%d')
            end_date = datetime.strptime(date_to, '%Y-%m-%d')
            end_date = end_date.replace(hour=23, minute=59, second=59)
            days = (end_date - start_date).days
        except:
            start_date = now - timedelta(days=days)
            end_date = now
    else:
        start_date = now - timedelta(days=days)
        end_date = now

    start_date_obj = start_date.date() if hasattr(start_date, 'date') else start_date
    end_date_obj = end_date.date() if hasattr(end_date, 'date') else end_date

    # ===== СОБИРАЕМ ДАННЫЕ =====
    total_stats = {
        'users': User.objects.count(),
        'posts': Post.objects.filter(status='published', is_hidden=False).count(),
        'comments': Comment.objects.filter(is_deleted=False, is_hidden=False).count(),
        'likes': Like.objects.filter(content_type='post').count(),
        'communities': Community.objects.filter(status='active').count(),
        'reports': Report.objects.filter(status='pending').count(),
    }

    period_stats = {
        'days': days,
        'start_date': start_date_obj.isoformat() if hasattr(start_date_obj, 'isoformat') else str(start_date_obj),
        'end_date': end_date_obj.isoformat() if hasattr(end_date_obj, 'isoformat') else str(end_date_obj),
        'new_users': User.objects.filter(date_joined__date__gte=start_date_obj,
                                         date_joined__date__lte=end_date_obj).count(),
        'new_posts': Post.objects.filter(created_at__date__gte=start_date_obj, created_at__date__lte=end_date_obj,
                                         status='published', is_hidden=False).count(),
        'new_comments': Comment.objects.filter(created_at__date__gte=start_date_obj, created_at__date__lte=end_date_obj,
                                               is_deleted=False, is_hidden=False).count(),
        'new_likes': Like.objects.filter(created_at__date__gte=start_date_obj, created_at__date__lte=end_date_obj,
                                         content_type='post').count(),
        'new_communities': Community.objects.filter(created_at__date__gte=start_date_obj,
                                                    created_at__date__lte=end_date_obj, status='active').count(),
    }

    # Ежедневная статистика
    daily_stats = []
    current = start_date_obj
    while current <= end_date_obj:
        daily_stats.append({
            'date': current.strftime('%d.%m'),
            'users': User.objects.filter(date_joined__date=current).count(),
            'posts': Post.objects.filter(created_at__date=current, status='published', is_hidden=False).count(),
            'comments': Comment.objects.filter(created_at__date=current, is_deleted=False, is_hidden=False).count(),
        })
        current += timedelta(days=1)

    # Топ пользователей
    user_stats = []
    for user in User.objects.all()[:50]:
        posts_count = Post.objects.filter(author=user, status='published', is_hidden=False).count()
        comments_count = Comment.objects.filter(author=user, is_deleted=False, is_hidden=False).count()
        if posts_count > 0 or comments_count > 0:
            user_stats.append({
                'username': user.username,
                'posts_count': posts_count,
                'comments_count': comments_count,
            })
    top_users = sorted(user_stats, key=lambda x: x['posts_count'], reverse=True)[:10]

    # Топ постов
    top_posts = []
    for post in Post.objects.filter(status='published', is_hidden=False).select_related('author').order_by(
            '-likes_count')[:10]:
        top_posts.append({
            'title': post.title,
            'author': post.author.username,
            'likes_count': post.likes_count,
            'comments_count': post.comments_count,
            'views_count': post.views_count,
        })

    # Топ сообществ
    from communities.models import CommunityPost
    community_stats = []
    for community in Community.objects.filter(status='active')[:10]:
        posts_count = CommunityPost.objects.filter(community=community, post__status='published',
                                                   post__is_hidden=False).count()
        community_stats.append({
            'name': community.name,
            'members_count': community.members.count(),
            'posts_count': posts_count,
        })
    top_communities = sorted(community_stats, key=lambda x: x['posts_count'], reverse=True)[:10]

    # Создаём PDF
    buffer = BytesIO()

    # Регистрируем шрифт
    font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans.ttf')
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
        pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', font_path))
        font_name = 'DejaVuSans'
        font_bold = 'DejaVuSans-Bold'
    else:
        font_name = 'Helvetica'
        font_bold = 'Helvetica-Bold'

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=8 * mm,
        leftMargin=8 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('CustomTitle', parent=styles['Normal'], fontName=font_bold, fontSize=20,
                                 textColor=colors.HexColor('#2563eb'), alignment=TA_CENTER, spaceAfter=10)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontName=font_name, fontSize=11,
                                    textColor=colors.HexColor('#6b7280'), alignment=TA_CENTER, spaceAfter=5)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Normal'], fontName=font_bold, fontSize=14,
                                   textColor=colors.HexColor('#1f2937'), spaceAfter=10, spaceBefore=15)
    normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontName=font_name, fontSize=9,
                                  alignment=TA_LEFT)
    center_style = ParagraphStyle('CenterStyle', parent=styles['Normal'], fontName=font_name, fontSize=9,
                                  alignment=TA_CENTER)
    meta_style = ParagraphStyle('MetaStyle', parent=styles['Normal'], fontName=font_name, fontSize=10,
                                textColor=colors.HexColor('#4b5563'), alignment=TA_CENTER, spaceAfter=3)

    elements = []

    # ========== ЗАГОЛОВОК ==========
    type_names = {
        'full': 'Полный отчёт',
        'summary': 'Краткий отчёт',
        'users': 'Топ пользователей',
        'posts': 'Топ постов',
        'communities': 'Топ сообществ',
        'daily': 'Ежедневная статистика'
    }
    type_display = type_names.get(export_type, 'Аналитика')

    elements.append(Paragraph(f"Аналитика платформы «Поток»", title_style))
    elements.append(Paragraph(f"{type_display}", subtitle_style))
    elements.append(Spacer(1, 5 * mm))

    # ========== МЕТАДАННЫЕ ОТЧЁТА ==========
    elements.append(Paragraph(f"<b>Период отчёта:</b> {start_date_obj.strftime('%d.%m.%Y')} — {end_date_obj.strftime('%d.%m.%Y')}", meta_style))
    elements.append(Paragraph(f"<b>Кто создал:</b> {request.user.get_full_name() or request.user.username} ({request.user.email})", meta_style))
    elements.append(Paragraph(f"<b>Дата создания:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}", meta_style))
    elements.append(Spacer(1, 10 * mm))

    if export_type in ['full', 'summary']:
        # Общая статистика
        elements.append(Paragraph("Общая статистика", heading_style))
        stats_data = [['Показатель', 'Значение']]
        stats_data.append(['Всего пользователей', str(total_stats['users'])])
        stats_data.append(['Всего постов', str(total_stats['posts'])])
        stats_data.append(['Всего комментариев', str(total_stats['comments'])])
        stats_data.append(['Всего лайков', str(total_stats['likes'])])
        stats_data.append(['Всего сообществ', str(total_stats['communities'])])
        stats_data.append(['Жалоб на модерации', str(total_stats['reports'])])

        stats_table = Table(stats_data, colWidths=[150, 90])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#2563eb')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
            ('ALIGN', (0, 0), (1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (1, 0), font_bold),
            ('FONTSIZE', (0, 0), (1, 0), 11),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(stats_table)
        elements.append(Spacer(1, 10 * mm))

        # Статистика за период
        elements.append(Paragraph("Статистика за период", heading_style))
        period_data = [['Показатель', 'Значение']]
        period_data.append(['Новых пользователей', str(period_stats['new_users'])])
        period_data.append(['Новых постов', str(period_stats['new_posts'])])
        period_data.append(['Новых комментариев', str(period_stats['new_comments'])])
        period_data.append(['Новых лайков', str(period_stats['new_likes'])])
        period_data.append(['Новых сообществ', str(period_stats['new_communities'])])

        period_table = Table(period_data, colWidths=[150, 90])
        period_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
            ('FONTNAME', (0, 0), (1, 0), font_bold),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(period_table)
        elements.append(Spacer(1, 10 * mm))

    if export_type in ['full', 'daily']:
        # Ежедневная активность
        elements.append(Paragraph("Ежедневная активность", heading_style))
        activity_data = [['Дата', 'Пользователи', 'Посты', 'Комментарии']]
        for day in daily_stats[-30:]:
            activity_data.append([day['date'], str(day['users']), str(day['posts']), str(day['comments'])])

        activity_table = Table(activity_data, colWidths=[65, 80, 70, 80])
        activity_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(activity_table)
        elements.append(Spacer(1, 10 * mm))

    if export_type in ['full', 'users']:
        # Топ пользователей
        elements.append(Paragraph("Топ-10 активных пользователей", heading_style))
        users_data = [['#', 'Пользователь', 'Посты', 'Комментарии']]
        for i, user in enumerate(top_users, 1):
            users_data.append([str(i), user['username'], str(user['posts_count']), str(user['comments_count'])])

        users_table = Table(users_data, colWidths=[35, 180, 80, 80])
        users_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(users_table)
        elements.append(Spacer(1, 10 * mm))

    if export_type in ['full', 'posts']:
        # Топ постов
        elements.append(Paragraph("Топ-10 популярных постов", heading_style))
        posts_data = [['#', 'Заголовок', 'Лайки', 'Комментарии', 'Просмотры']]
        for i, post in enumerate(top_posts, 1):
            title = post['title'][:100] + '...' if len(post['title']) > 100 else post['title']
            posts_data.append(
                [str(i), title, str(post['likes_count']), str(post['comments_count']), str(post['views_count'])])

        posts_table = Table(posts_data, colWidths=[35, 300, 60, 70, 70])
        posts_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(posts_table)
        elements.append(Spacer(1, 10 * mm))

    if export_type in ['full', 'communities']:
        # Топ сообществ
        elements.append(Paragraph("Топ-10 активных сообществ", heading_style))
        communities_data = [['#', 'Название', 'Участников', 'Постов']]
        for i, community in enumerate(top_communities, 1):
            name = community['name'][:60] + '...' if len(community['name']) > 60 else community['name']
            communities_data.append(
                [str(i), name, str(community['members_count']), str(community['posts_count'])])

        communities_table = Table(communities_data, colWidths=[35, 260, 80, 80])
        communities_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(communities_table)

    # ========== ПОДВАЛ ==========
    elements.append(Spacer(1, 15 * mm))
    elements.append(Paragraph("<i>Отчёт сгенерирован автоматически системой «Поток»</i>", center_style))

    # Собираем PDF
    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response[
        'Content-Disposition'] = f'attachment; filename="analytics_{export_type}_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf"'
    return response

@staff_member_required
def export_analytics_json(request):
    """Экспорт аналитики в JSON с фильтрами"""

    # ===== ПОЛУЧАЕМ ПАРАМЕТРЫ ФИЛЬТРАЦИИ =====
    days = int(request.GET.get('days', 30))
    export_type = request.GET.get('type', 'full')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    now = timezone.now()

    # Обработка кастомных дат
    if date_from and date_to:
        try:
            from datetime import datetime
            start_date = datetime.strptime(date_from, '%Y-%m-%d')
            end_date = datetime.strptime(date_to, '%Y-%m-%d')
            end_date = end_date.replace(hour=23, minute=59, second=59)
            days = (end_date - start_date).days
        except:
            start_date = now - timedelta(days=days)
            end_date = now
    else:
        start_date = now - timedelta(days=days)
        end_date = now

    # Преобразуем даты для фильтрации
    start_date_obj = start_date.date() if hasattr(start_date, 'date') else start_date
    end_date_obj = end_date.date() if hasattr(end_date, 'date') else end_date

    # ===== 1. ОБЩАЯ СТАТИСТИКА =====
    total_stats = {
        'users': User.objects.count(),
        'posts': Post.objects.filter(status='published', is_hidden=False).count(),
        'comments': Comment.objects.filter(is_deleted=False, is_hidden=False).count(),
        'likes': Like.objects.filter(content_type='post').count(),
        'communities': Community.objects.filter(status='active').count(),
        'reports': Report.objects.filter(status='pending').count(),
        'bans': Ban.objects.filter(expires_at__gt=now).count(),
        'categories': Category.objects.count(),
        'tags': Tag.objects.count(),
    }

    # ===== 2. СТАТИСТИКА ЗА ПЕРИОД =====
    period_stats = {
        'days': days,
        'start_date': start_date_obj.isoformat() if hasattr(start_date_obj, 'isoformat') else str(start_date_obj),
        'end_date': end_date_obj.isoformat() if hasattr(end_date_obj, 'isoformat') else str(end_date_obj),
        'new_users': User.objects.filter(date_joined__date__gte=start_date_obj,
                                         date_joined__date__lte=end_date_obj).count(),
        'new_posts': Post.objects.filter(created_at__date__gte=start_date_obj, created_at__date__lte=end_date_obj,
                                         status='published', is_hidden=False).count(),
        'new_comments': Comment.objects.filter(created_at__date__gte=start_date_obj, created_at__date__lte=end_date_obj,
                                               is_deleted=False, is_hidden=False).count(),
        'new_likes': Like.objects.filter(created_at__date__gte=start_date_obj, created_at__date__lte=end_date_obj,
                                         content_type='post').count(),
        'new_communities': Community.objects.filter(created_at__date__gte=start_date_obj,
                                                    created_at__date__lte=end_date_obj, status='active').count(),
    }

    # ===== 3. ЕЖЕДНЕВНАЯ СТАТИСТИКА =====
    daily_stats = []
    current = start_date_obj
    while current <= end_date_obj:
        daily_stats.append({
            'date': current.strftime('%Y-%m-%d'),
            'users': User.objects.filter(date_joined__date=current).count(),
            'posts': Post.objects.filter(created_at__date=current, status='published', is_hidden=False).count(),
            'comments': Comment.objects.filter(created_at__date=current, is_deleted=False, is_hidden=False).count(),
            'likes': Like.objects.filter(created_at__date=current, content_type='post').count(),
        })
        current += timedelta(days=1)

    # ===== 4. ТОП-10 ПОЛЬЗОВАТЕЛЕЙ =====
    from collections import defaultdict
    user_stats = []
    for user in User.objects.all()[:50]:
        posts_count = Post.objects.filter(author=user, status='published', is_hidden=False).count()
        comments_count = Comment.objects.filter(author=user, is_deleted=False, is_hidden=False).count()
        if posts_count > 0 or comments_count > 0:
            user_stats.append({
                'id': user.id,
                'username': user.username,
                'full_name': user.get_full_name(),
                'posts_count': posts_count,
                'comments_count': comments_count,
                'joined_at': user.date_joined.isoformat(),
            })
    top_users = sorted(user_stats, key=lambda x: x['posts_count'], reverse=True)[:10]

    # ===== 5. ТОП-10 ПОСТОВ =====
    top_posts = []
    for post in Post.objects.filter(status='published', is_hidden=False).select_related('author').order_by(
            '-likes_count')[:10]:
        top_posts.append({
            'id': post.id,
            'title': post.title,
            'author': post.author.username,
            'likes_count': post.likes_count,
            'comments_count': post.comments_count,
            'views_count': post.views_count,
            'created_at': post.created_at.isoformat(),
        })

    # ===== 6. ТОП-10 СООБЩЕСТВ =====
    top_communities = []
    for community in Community.objects.filter(status='active')[:10]:
        # Считаем посты через CommunityPost
        from communities.models import CommunityPost
        posts_count = CommunityPost.objects.filter(
            community=community,
            post__status='published',
            post__is_hidden=False
        ).count()

        top_communities.append({
            'id': community.id,
            'name': community.name,
            'slug': community.slug,
            'members_count': community.members.count(),
            'posts_count': posts_count,
            'created_at': community.created_at.isoformat(),
        })
    top_communities = sorted(top_communities, key=lambda x: x['posts_count'], reverse=True)[:10]

    # ===== 7. АКТИВНОСТЬ ПО ДНЯМ НЕДЕЛИ =====
    weekday_stats = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
    for post in Post.objects.filter(created_at__date__gte=start_date_obj, created_at__date__lte=end_date_obj,
                                    status='published'):
        weekday_stats[post.created_at.weekday()] += 1

    weekdays = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
    weekday_activity = [{'day': weekdays[i], 'count': weekday_stats[i]} for i in range(7)]

    # ===== 8. ФОРМИРУЕМ ИТОГОВЫЙ JSON =====
    export_data = {
        'export_info': {
            'exported_at': now.isoformat(),
            'exported_by': request.user.username,
            'export_type': export_type,
        },
        'filter_info': {
            'days': days,
            'start_date': start_date_obj.isoformat() if hasattr(start_date_obj, 'isoformat') else str(start_date_obj),
            'end_date': end_date_obj.isoformat() if hasattr(end_date_obj, 'isoformat') else str(end_date_obj),
        }
    }

    if export_type in ['full', 'summary']:
        export_data['total_stats'] = total_stats
        export_data['period_stats'] = period_stats

    if export_type in ['full', 'daily']:
        export_data['daily_stats'] = daily_stats
        export_data['weekday_activity'] = weekday_activity

    if export_type in ['full', 'users']:
        export_data['top_users'] = top_users

    if export_type in ['full', 'posts']:
        export_data['top_posts'] = top_posts

    if export_type in ['full', 'communities']:
        export_data['top_communities'] = top_communities

    return JsonResponse(export_data, json_dumps_params={'ensure_ascii': False, 'indent': 2})