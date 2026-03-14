from django import forms
from django.core.exceptions import ValidationError
from .models import Community, CommunityPost
from posts.models import Post


class CommunityForm(forms.ModelForm):
    """
    Форма создания/редактирования сообщества
    """

    class Meta:
        model = Community
        fields = ['name', 'description', 'avatar', 'cover', 'privacy', 'categories', 'tags']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Название сообщества'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Описание сообщества...'
            }),
            'avatar': forms.FileInput(attrs={
                'class': 'form-control'
            }),
            'cover': forms.FileInput(attrs={
                'class': 'form-control'
            }),
            'privacy': forms.Select(attrs={
                'class': 'form-control'
            }),
            'categories': forms.SelectMultiple(attrs={
                'class': 'form-control'
            }),
            'tags': forms.SelectMultiple(attrs={
                'class': 'form-control'
            }),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if len(name) < 3:
            raise ValidationError('Название должно содержать минимум 3 символа')
        return name


class CommunityPostForm(forms.ModelForm):
    """
    Форма создания поста в сообществе
    """
    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Заголовок поста'
        })
    )
    content = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 10,
            'placeholder': 'Содержание поста...',
            'required': 'required'
    })
    )
    image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control'
        })
    )
    video = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control'
        })
    )
    is_pinned = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    is_announcement = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )

    class Meta:
        model = Post
        fields = ['title', 'content', 'image', 'video']

    def save(self, community, author, commit=True):
        post = super().save(commit=False)
        post.author = author
        post.status = 'published'

        if commit:
            post.save()
            # Создаем связь с сообществом
            CommunityPost.objects.create(
                post=post,
                community=community,
                is_pinned=self.cleaned_data['is_pinned'],
                is_announcement=self.cleaned_data['is_announcement']
            )
        return post


class CommunityJoinRequestForm(forms.Form):
    """
    Форма заявки на вступление
    """
    message = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Расскажите, почему вы хотите вступить (необязательно)'
        })
    )