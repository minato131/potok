from django import forms
from django.core.exceptions import ValidationError
from .models import Post, Comment, Category, Tag


class PostForm(forms.ModelForm):
    """
    Форма создания/редактирования поста
    """
    class Meta:
        model = Post
        fields = ['title', 'content', 'category', 'tags', 'image', 'video', 'status']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите заголовок'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 10,
                'placeholder': 'Содержание поста...'
            }),
            'category': forms.Select(attrs={
                'class': 'form-control'
            }),
            'tags': forms.SelectMultiple(attrs={
                'class': 'form-control'
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control'
            }),
            'video': forms.FileInput(attrs={
                'class': 'form-control'
            }),
            'status': forms.Select(attrs={
                'class': 'form-control'
            }),
        }

    def clean_title(self):
        title = self.cleaned_data.get('title')
        if len(title) < 5:
            raise ValidationError('Заголовок должен содержать минимум 5 символов')
        return title

    def clean_content(self):
        content = self.cleaned_data.get('content')
        if len(content) < 10:
            raise ValidationError('Содержание должно содержать минимум 10 символов')
        return content


class CommentForm(forms.ModelForm):
    """
    Форма комментария
    """
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Напишите комментарий...'
            }),
        }

    def clean_content(self):
        content = self.cleaned_data.get('content')
        if len(content) < 2:
            raise ValidationError('Комментарий слишком короткий')
        return content


class PostSearchForm(forms.Form):
    """
    Форма поиска постов
    """
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Поиск постов...'
        })
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    tag = forms.ModelChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    author = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Автор...'
        })
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    ordering = forms.ChoiceField(
        choices=[
            ('-created_at', 'Новые'),
            ('created_at', 'Старые'),
            ('-views_count', 'Просмотры'),
            ('-likes_count', 'Лайки'),
            ('title', 'По заголовку'),
        ],
        required=False,
        initial='-created_at',  # <-- добавили значение по умолчанию
        widget=forms.Select(attrs={'class': 'form-control'})
    )