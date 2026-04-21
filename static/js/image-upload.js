// static/js/image-upload.js
function initImageUpload(containerId, inputName, previewId) {
    const container = document.getElementById(containerId);
    const input = document.querySelector(`input[name="${inputName}"]`);
    const preview = document.getElementById(previewId);

    if (!container || !input) return;

    // Клик по контейнеру
    container.addEventListener('click', (e) => {
        if (e.target.tagName !== 'BUTTON' && !e.target.closest('button')) {
            input.click();
        }
    });

    // Drag & Drop
    container.addEventListener('dragover', (e) => {
        e.preventDefault();
        container.classList.add('dragover');
    });

    container.addEventListener('dragleave', () => {
        container.classList.remove('dragover');
    });

    container.addEventListener('drop', (e) => {
        e.preventDefault();
        container.classList.remove('dragover');

        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            input.files = e.dataTransfer.files;
            handleImagePreview(file, preview, container);
        }
    });

    // Выбор файла
    input.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            handleImagePreview(file, preview, container);
        }
    });

    function handleImagePreview(file, previewElement, containerElement) {
        const reader = new FileReader();
        reader.onload = function(e) {
            if (previewElement) {
                if (previewElement.tagName === 'IMG') {
                    previewElement.src = e.target.result;
                } else {
                    // Заменяем плейсхолдер на изображение
                    const img = document.createElement('img');
                    img.src = e.target.result;
                    img.id = previewElement.id;
                    img.alt = 'Preview';
                    previewElement.parentNode.replaceChild(img, previewElement);
                }
            }

            // Скрываем плейсхолдер если он есть
            const placeholder = containerElement.querySelector('.upload-placeholder, .preview-placeholder');
            if (placeholder) {
                placeholder.style.display = 'none';
            }

            // Показываем превью
            const previewContainer = containerElement.querySelector('.image-preview-container');
            if (previewContainer) {
                previewContainer.style.display = 'block';
            }
        };
        reader.readAsDataURL(file);
    }
}

// Автоматическая инициализация для всех загрузчиков
document.addEventListener('DOMContentLoaded', function() {
    // Для постов
    initImageUpload('imageUploadArea', 'image', 'imagePreview');

    // Для аватара в профиле
    initImageUpload('avatarPreview', 'avatar', 'avatarPreview');

    // Для обложки в профиле
    initImageUpload('coverPreview', 'cover_image', 'coverPreview');

    // Для аватара сообщества
    initImageUpload('avatarPreview', 'avatar', 'avatarPreview');

    // Для обложки сообщества
    initImageUpload('coverPreview', 'cover_image', 'coverPreview');
});