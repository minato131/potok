from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q, F, Sum
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse

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
    """Экспорт аналитики в PDF"""
    days = int(request.GET.get('days', 30))
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)

    # Собираем данные
    users_by_day = []
    posts_by_day = []
    comments_by_day = []
    dates = []

    current = start_date
    while current <= end_date:
        dates.append(current.strftime('%d.%m'))
        users_by_day.append(User.objects.filter(date_joined__date=current.date()).count())
        posts_by_day.append(Post.objects.filter(created_at__date=current.date()).count())
        comments_by_day.append(Comment.objects.filter(created_at__date=current.date()).count())
        current += timedelta(days=1)

    # Топ пользователей
    top_users = User.objects.annotate(
        posts_count=Count('posts', filter=Q(posts__status='published')),
        comments_count=Count('comments', filter=Q(comments__is_deleted=False)),
        total_activity=Count('posts') + Count('comments') * 2
    ).order_by('-total_activity')[:10]

    # Топ постов
    top_posts = Post.objects.filter(status='published').annotate(
        total_score=F('likes_count') * 2 + F('comments_count') * 3 + F('views_count')
    ).order_by('-total_score')[:10]

    # Общая статистика
    from communities.models import Community
    from moderation.models import Report

    total_stats = {
        'users': User.objects.count(),
        'posts': Post.objects.filter(status='published').count(),
        'comments': Comment.objects.filter(is_deleted=False).count(),
        'likes': Like.objects.count(),
        'communities': Community.objects.filter(status='active').count(),
        'reports': Report.objects.filter(status='pending').count(),
    }

    # Создаём PDF
    buffer = BytesIO()

    # Регистрируем шрифт DejaVuSans для поддержки кириллицы
    font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans.ttf')

    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
        pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', font_path))
        font_name = 'DejaVuSans'
        font_bold = 'DejaVuSans-Bold'
        print(f"Шрифт загружен: {font_path}")
    else:
        # Fallback на стандартный шрифт Helvetica
        font_name = 'Helvetica'
        font_bold = 'Helvetica-Bold'
        print(f"Шрифт не найден: {font_path}, используем {font_name}")

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm
    )

    # Стили с поддержкой кириллицы
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Normal'],
        fontName=font_bold,
        fontSize=20,
        textColor=colors.HexColor('#2563eb'),
        alignment=TA_CENTER,
        spaceAfter=20
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Normal'],
        fontName=font_bold,
        fontSize=14,
        textColor=colors.HexColor('#1f2937'),
        spaceAfter=10,
        spaceBefore=15
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=9,
        alignment=TA_LEFT
    )

    center_style = ParagraphStyle(
        'CenterStyle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=9,
        alignment=TA_CENTER
    )

    # Элементы документа
    elements = []

    # Заголовок
    elements.append(Paragraph("Аналитика платформы Поток", title_style))
    elements.append(
        Paragraph(f"Период: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}", center_style))
    elements.append(Paragraph(f"Дата выгрузки: {datetime.now().strftime('%d.%m.%Y %H:%M')}", center_style))
    elements.append(Spacer(1, 15 * mm))

    # Общая статистика
    elements.append(Paragraph("Общая статистика", heading_style))

    stats_data = [
        ['Показатель', 'Значение'],
        ['Пользователей', str(total_stats['users'])],
        ['Постов', str(total_stats['posts'])],
        ['Комментариев', str(total_stats['comments'])],
        ['Лайков', str(total_stats['likes'])],
        ['Сообществ', str(total_stats['communities'])],
        ['Жалоб на рассмотрении', str(total_stats['reports'])],
    ]

    stats_table = Table(stats_data, colWidths=[100, 80])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#2563eb')),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('ALIGN', (0, 0), (1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (1, 0), font_bold),
        ('FONTSIZE', (0, 0), (1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f9fafb')),
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -1), font_name),
    ]))
    elements.append(stats_table)
    elements.append(Spacer(1, 10 * mm))

    # Активность по дням
    if any(users_by_day) or any(posts_by_day) or any(comments_by_day):
        elements.append(Paragraph("Динамика активности", heading_style))

        display_dates = dates[-30:] if len(dates) > 30 else dates
        display_users = users_by_day[-30:] if len(users_by_day) > 30 else users_by_day
        display_posts = posts_by_day[-30:] if len(posts_by_day) > 30 else posts_by_day
        display_comments = comments_by_day[-30:] if len(comments_by_day) > 30 else comments_by_day

        activity_data = [['Дата', 'Пользователи', 'Посты', 'Комментарии']]
        for i in range(len(display_dates)):
            activity_data.append([
                display_dates[i],
                str(display_users[i]),
                str(display_posts[i]),
                str(display_comments[i])
            ])

        activity_table = Table(activity_data, colWidths=[50, 60, 50, 60])
        activity_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
        ]))
        elements.append(activity_table)
        elements.append(Spacer(1, 10 * mm))

    # Топ пользователей
    if top_users:
        elements.append(Paragraph("Топ-10 активных пользователей", heading_style))

        users_data = [['#', 'Пользователь', 'Посты', 'Комментарии', 'Активность']]
        for i, user in enumerate(top_users, 1):
            users_data.append([
                str(i),
                user.username,
                str(user.posts_count),
                str(user.comments_count),
                str(user.total_activity)
            ])

        users_table = Table(users_data, colWidths=[30, 100, 50, 60, 60])
        users_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
        ]))
        elements.append(users_table)
        elements.append(Spacer(1, 10 * mm))

    # Топ постов
    if top_posts:
        elements.append(Paragraph("Топ-10 популярных постов", heading_style))

        posts_data = [['#', 'Заголовок', 'Лайки', 'Комментарии', 'Просмотры']]
        for i, post in enumerate(top_posts, 1):
            title = post.title[:60] + '...' if len(post.title) > 60 else post.title
            posts_data.append([
                str(i),
                title,
                str(post.likes_count),
                str(post.comments_count),
                str(post.views_count)
            ])

        posts_table = Table(posts_data, colWidths=[30, 180, 50, 60, 60])
        posts_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), font_name),
        ]))
        elements.append(posts_table)

    # Собираем PDF
    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="analytics_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf"'
    return response