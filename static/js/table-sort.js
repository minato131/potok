// static/js/table-sort.js
function initTableSort(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;

    const headers = table.querySelectorAll('th[data-sort]');
    let currentSort = { column: null, direction: 'asc' };

    headers.forEach(header => {
        header.style.cursor = 'pointer';
        header.addEventListener('click', function() {
            const column = this.dataset.sort;
            const direction = currentSort.column === column && currentSort.direction === 'asc' ? 'desc' : 'asc';

            // Обновляем иконки
            headers.forEach(h => {
                h.classList.remove('sort-asc', 'sort-desc');
            });
            this.classList.add(`sort-${direction}`);

            // Сортируем
            sortTable(table, column, direction);

            currentSort = { column, direction };
        });
    });
}

function sortTable(table, column, direction) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {
        const aVal = a.querySelector(`td[data-${column}]`)?.dataset[column] ||
                     a.cells[getColumnIndex(table, column)]?.textContent || '';
        const bVal = b.querySelector(`td[data-${column}]`)?.dataset[column] ||
                     b.cells[getColumnIndex(table, column)]?.textContent || '';

        // Числовое сравнение
        if (!isNaN(aVal) && !isNaN(bVal)) {
            return direction === 'asc' ? aVal - bVal : bVal - aVal;
        }

        // Строковое сравнение
        return direction === 'asc'
            ? aVal.localeCompare(bVal)
            : bVal.localeCompare(aVal);
    });

    // Перестраиваем таблицу
    rows.forEach(row => tbody.appendChild(row));
}

function getColumnIndex(table, columnName) {
    const headers = table.querySelectorAll('th');
    for (let i = 0; i < headers.length; i++) {
        if (headers[i].dataset.sort === columnName) {
            return i;
        }
    }
    return 0;
}

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', function() {
    initTableSort('reportsTable');
    initTableSort('usersTable');
});