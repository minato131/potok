from django import forms
from django.core.exceptions import ValidationError
from .models import Post, Comment, Category, Tag


class PostForm(forms.ModelForm):
    """
    Форма создания/редактирования поста
    """
    tags_input = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'tagsInput'}),
        help_text='Теги через запятую'
    )

    class Meta:
        model = Post
        fields = ['title', 'content', 'category', 'image', 'video']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Введите заголовок поста'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 10,
                'placeholder': 'Содержание поста...'
            }),
            'category': forms.Select(attrs={
                'class': 'form-select'
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-input',
                'accept': 'image/*'
            }),
            'video': forms.FileInput(attrs={
                'class': 'form-input',
                'accept': 'video/*'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].required = False
        self.fields['image'].required = False
        self.fields['video'].required = False

    def clean_title(self):
        title = self.cleaned_data.get('title')
        if not title:
            raise ValidationError('Заголовок обязателен')
        if len(title) < 5:
            raise ValidationError('Заголовок должен содержать минимум 5 символов')
        return title

    def clean_content(self):
        content = self.cleaned_data.get('content')
        if not content or len(content.strip()) < 10:
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


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите название тега'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data.get('name')
        name = name.strip().lower().replace(' ', '-')

        # Проверяем существование тега
        if Tag.objects.filter(name=name).exists():
            raise ValidationError('Тег с таким названием уже существует')

        return name

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'parent', 'order']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Название категории'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Описание категории'
            }),
            'parent': forms.Select(attrs={
                'class': 'form-control'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['parent'].queryset = Category.objects.exclude(id=self.instance.id)