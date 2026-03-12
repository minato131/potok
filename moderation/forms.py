from django import forms
from django.core.exceptions import ValidationError
from .models import Report, Ban
from django.contrib.contenttypes.models import ContentType
from posts.models import Post, Comment
from communities.models import Community


class ReportForm(forms.ModelForm):
    """
    Форма создания жалобы
    """

    class Meta:
        model = Report
        fields = ['report_type', 'description']
        widgets = {
            'report_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Опишите причину жалобы подробнее...'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.content_object = kwargs.pop('content_object', None)
        self.reporter = kwargs.pop('reporter', None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        report = super().save(commit=False)
        if self.reporter:
            report.reporter = self.reporter
        if self.content_object:
            report.content_object = self.content_object
        if commit:
            report.save()
        return report


class BanForm(forms.ModelForm):
    """
    Форма блокировки пользователя
    """

    class Meta:
        model = Ban
        fields = ['ban_type', 'reason', 'expires_at']
        widgets = {
            'ban_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Укажите причину блокировки'
            }),
            'expires_at': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        ban_type = cleaned_data.get('ban_type')
        expires_at = cleaned_data.get('expires_at')

        if ban_type == 'temporary' and not expires_at:
            raise ValidationError('Для временной блокировки укажите дату истечения')

        if ban_type == 'permanent' and expires_at:
            cleaned_data['expires_at'] = None

        return cleaned_data


class ModerationActionForm(forms.Form):
    """
    Форма для массовых действий модератора
    """
    ACTION_CHOICES = [
        ('approve', 'Одобрить жалобы'),
        ('reject', 'Отклонить жалобы'),
        ('hide', 'Скрыть контент'),
        ('delete', 'Удалить контент'),
    ]

    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Комментарий модератора...'
        })
    )