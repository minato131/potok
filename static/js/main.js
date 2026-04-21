// static/js/main.js
document.addEventListener('DOMContentLoaded', function() {
    // Мобильное меню
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
        mobileNavClose.addEventListener('click', closeMenu);
        mobileNavOverlay.addEventListener('click', closeMenu);

        // Закрытие по Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && mobileNav.classList.contains('active')) {
                closeMenu();
            }
        });
    }

    // Подсветка активного пункта меню (уже сделано в шаблоне, но можно добавить динамику)

    // Автоматическое скрытие алертов через 5 секунд
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.3s ease';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });
});