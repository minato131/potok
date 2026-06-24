# communities/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from .models import Community, CommunityPost, CommunityJoinRequest
from posts.models import Post, Tag


class CommunityForm(forms.ModelForm):
    """
    Форма создания/редактирования сообщества
    """

    class Meta:
        model = Community
        fields = ['name', 'slug', 'description', 'rules', 'avatar', 'cover',
                  'community_type', 'privacy', 'website', 'discord', 'telegram',
                  'category', 'posts_need_approval']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Название сообщества'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'url-адрес'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
                'placeholder': 'Описание сообщества'
            }),
            'rules': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 6,
                'placeholder': 'Правила сообщества...'
            }),
            'community_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'privacy': forms.Select(attrs={
                'class': 'form-select'
            }),
            'website': forms.URLInput(attrs={
                'class': 'form-input',
                'placeholder': 'https://example.com'
            }),
            'discord': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Discord ссылка или ID'
            }),
            'telegram': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '@username или ссылка'
            }),
            'category': forms.Select(attrs={
                'class': 'form-select'
            }),
            'posts_need_approval': forms.CheckboxInput(attrs={
                'class': 'checkbox-input'
            }),
        }

    def clean_slug(self):
        slug = self.cleaned_data.get('slug')
        if slug:
            slug = slugify(slug)
            # Проверяем уникальность, исключая текущий объект
            if self.instance.pk:
                if Community.objects.exclude(pk=self.instance.pk).filter(slug=slug).exists():
                    raise ValidationError('Сообщество с таким URL уже существует')
            else:
                if Community.objects.filter(slug=slug).exists():
                    raise ValidationError('Сообщество с таким URL уже существует')
        return slug

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            # Проверяем уникальность имени
            if self.instance.pk:
                if Community.objects.exclude(pk=self.instance.pk).filter(name__iexact=name).exists():
                    raise ValidationError('Сообщество с таким названием уже существует')
            else:
                if Community.objects.filter(name__iexact=name).exists():
                    raise ValidationError('Сообщество с таким названием уже существует')
        return name


class CommunityPostForm(forms.Form):
    """Форма создания поста в сообществе (с медиа)"""
    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Заголовок поста'
        })
    )
    content = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 8,
            'placeholder': 'Содержание поста...'
        })
    )
    image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-input',
            'accept': 'image/*'
        })
    )
    image2 = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-input',
            'accept': 'image/*'
        })
    )
    image3 = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-input',
            'accept': 'image/*'
        })
    )
    image4 = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-input',
            'accept': 'image/*'
        })
    )
    image5 = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-input',
            'accept': 'image/*'
        })
    )
    video = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-input',
            'accept': 'video/*'
        })
    )
    video2 = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-input',
            'accept': 'video/*'
        })
    )
    tags = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'python, django, программирование'
        })
    )

    def clean_title(self):
        title = self.cleaned_data.get('title')
        if not title or len(title.strip()) < 3:
            raise ValidationError('Заголовок должен быть не менее 3 символов')
        return title.strip()

    def clean_content(self):
        content = self.cleaned_data.get('content')
        # Контент не обязателен, если есть медиа
        if not content and not self.cleaned_data.get('image') and not self.cleaned_data.get('video'):
            raise ValidationError('Добавьте текст или медиафайл')
        return content

    def save(self, community, author):
        """
        Сохраняет пост и связывает с сообществом
        """
        from posts.models import Post, Tag
        from .models import CommunityPost

        # Создаём пост
        post = Post.objects.create(
            title=self.cleaned_data['title'],
            content=self.cleaned_data.get('content', ''),
            author=author,
            image=self.cleaned_data.get('image'),
            image2=self.cleaned_data.get('image2'),
            image3=self.cleaned_data.get('image3'),
            image4=self.cleaned_data.get('image4'),
            image5=self.cleaned_data.get('image5'),
            video=self.cleaned_data.get('video'),
            video2=self.cleaned_data.get('video2'),
            status='published'
        )

        # Обработка тегов
        tags_data = self.cleaned_data.get('tags', '')
        if tags_data:
            tag_names = [tag.strip().lower() for tag in tags_data.split(',') if tag.strip()]
            for tag_name in tag_names:
                tag, created = Tag.objects.get_or_create(name=tag_name)
                if not tag.slug:
                    from django.utils.text import slugify
                    tag.slug = slugify(tag_name)
                    tag.save()
                post.tags.add(tag)

        # Связываем с сообществом
        CommunityPost.objects.create(
            community=community,
            post=post,
            is_pinned=False,
            is_announcement=False
        )

        return post


class CommunityJoinRequestForm(forms.ModelForm):
    """
    Форма заявки на вступление в закрытое сообщество
    """

    class Meta:
        model = CommunityJoinRequest
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Расскажите о себе...'
            })
        }