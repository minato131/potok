from django import forms
from django.core.exceptions import ValidationError
from .models import Community, CommunityPost
from posts.models import Post


from django import forms
from django.core.exceptions import ValidationError
from .models import Community, CommunityPost
from posts.models import Post


class CommunityForm(forms.ModelForm):
    """
    Форма создания/редактирования сообщества
    """
    # Поля вручную с нужными классами
    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Название сообщества'})
    )
    slug = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'url-soobshchestva'})
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4, 'placeholder': 'Опишите сообщество...'})
    )
    avatar = forms.ImageField(required=False)
    cover = forms.ImageField(required=False)
    privacy = forms.ChoiceField(
        choices=Community.PRIVACY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    category = forms.ModelChoiceField(
        queryset=None,  # будет установлено в __init__
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    posts_need_approval = forms.BooleanField(required=False)
    rules = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4, 'placeholder': 'Правила сообщества...'})
    )
    website = forms.URLField(required=False, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'https://...'}))
    discord = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'discord.gg/...'}))
    telegram = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': '@username или t.me/...'}))

    class Meta:
        model = Community
        fields = ['name', 'slug', 'description', 'avatar', 'cover', 'privacy',
                   'category', 'posts_need_approval', 'rules',
                  'website', 'discord', 'telegram']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from posts.models import Category
        self.fields['category'].queryset = Category.objects.all()

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
            'class': 'form-input',
            'placeholder': 'Заголовок поста'
        })
    )
    content = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'rows': 10,
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
    video = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-input',
            'accept': 'video/*'
        })
    )
    is_pinned = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'checkbox-input'
        })
    )
    is_announcement = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'checkbox-input'
        })
    )

    class Meta:
        model = Post
        fields = ['title', 'content', 'image', 'video']

    def clean_content(self):
        content = self.cleaned_data.get('content')
        if not content or len(content.strip()) < 10:
            raise ValidationError('Содержание поста должно быть не менее 10 символов')
        return content

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
                is_pinned=self.cleaned_data.get('is_pinned', False),
                is_announcement=self.cleaned_data.get('is_announcement', False)
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