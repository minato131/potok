// static/js/main.js
document.addEventListener('DOMContentLoaded', function() {
    // Мобильное меню
    initMobileMenu();

    // Система уведомлений (toast)
    initToastSystem();

    // Ленивая загрузка изображений
    initLazyLoading();

    // Анимации при скролле
    initScrollAnimations();

    // Автоматическое скрытие алертов
    initAlertAutoHide();
});

function initMobileMenu() {
    const mobileMenuToggle = document.getElementById('mobileMenuToggle');
    const mobileNav = document.getElementById('mobileNav');
    const mobileNavOverlay = document.getElementById('mobileNavOverlay');
    const mobileNavClose = document.getElementById('mobileNavClose');

    if (mobileMenuToggle && mobileNav && mobileNavOverlay) {
        const openMenu = () => {
            mobileNav.classList.add('active');
            mobileNavOverlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        };

        const closeMenu = () => {
            mobileNav.classList.remove('active');
            mobileNavOverlay.classList.remove('active');
            document.body.style.overflow = '';
        };

        mobileMenuToggle.addEventListener('click', openMenu);
        mobileNavClose?.addEventListener('click', closeMenu);
        mobileNavOverlay.addEventListener('click', closeMenu);

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && mobileNav.classList.contains('active')) {
                closeMenu();
            }
        });
    }
}

function initToastSystem() {
    window.showToast = function(options) {
        const { type = 'info', title, message, duration = 5000 } = options;

        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `toast toast--${type}`;

        const icons = {
            success: 'check-circle',
            error: 'alert-circle',
            warning: 'alert-triangle',
            info: 'info'
        };

        toast.innerHTML = `
            <div class="toast__icon">
                <i data-feather="${icons[type] || 'info'}"></i>
            </div>
            <div class="toast__content">
                ${title ? `<div class="toast__title">${title}</div>` : ''}
                <div class="toast__message">${message}</div>
            </div>
            <button class="toast__close">
                <i data-feather="x"></i>
            </button>
        `;

        container.appendChild(toast);
        feather.replace();

        const closeBtn = toast.querySelector('.toast__close');
        closeBtn.addEventListener('click', () => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        });

        if (duration > 0) {
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.style.animation = 'slideIn 0.3s ease reverse';
                    setTimeout(() => toast.remove(), 300);
                }
            }, duration);
        }
    };
}

function initLazyLoading() {
    const images = document.querySelectorAll('img[data-src]');

    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.removeAttribute('data-src');
                observer.unobserve(img);
            }
        });
    });

    images.forEach(img => imageObserver.observe(img));
}

function initScrollAnimations() {
    const animatedElements = document.querySelectorAll('.fade-in-up');

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.animationPlayState = 'running';
                observer.unobserve(entry.target);
            }
        });
    });

    animatedElements.forEach(el => {
        el.style.animationPlayState = 'paused';
        observer.observe(el);
    });
}

function initAlertAutoHide() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.3s ease';
            alert.style.opacity = '0';
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.remove();
                }
            }, 300);
        }, 5000);
    });
}

// Вспомогательная функция для получения CSRF токена
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Функция для debounce
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Функция для форматирования даты
function formatDate(date) {
    const now = new Date();
    const diff = now - new Date(date);
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 7) {
        return new Date(date).toLocaleDateString('ru-RU');
    } else if (days > 0) {
        return `${days} ${pluralize(days, 'день', 'дня', 'дней')} назад`;
    } else if (hours > 0) {
        return `${hours} ${pluralize(hours, 'час', 'часа', 'часов')} назад`;
    } else if (minutes > 0) {
        return `${minutes} ${pluralize(minutes, 'минуту', 'минуты', 'минут')} назад`;
    } else {
        return 'только что';
    }
}

function pluralize(count, one, two, five) {
    const mod10 = count % 10;
    const mod100 = count % 100;

    if (mod10 === 1 && mod100 !== 11) {
        return one;
    } else if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) {
        return two;
    } else {
        return five;
    }
}

// Экспорт функций в глобальную область
window.getCookie = getCookie;
window.debounce = debounce;
window.formatDate = formatDate;