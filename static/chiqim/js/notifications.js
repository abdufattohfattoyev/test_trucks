document.addEventListener('DOMContentLoaded', function() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    const sortSelect = document.getElementById('sort-select');
    const groupSelect = document.getElementById('group-select');
    const statusFilter = document.getElementById('status-filter');
    const xaridorFilter = document.getElementById('xaridor-filter');
    const notificationsList = document.querySelector('.notifications-list');

    function updateNotifications() {
        const days = document.querySelector('.filter-btn.active')?.dataset.days || '30';
        const sort = sortSelect.value;
        const group = groupSelect.value;
        const status = statusFilter.value;
        const xaridor = xaridorFilter.value;

        const url = new URL(window.location.href);
        url.searchParams.set('days', days);
        url.searchParams.set('sort', sort);
        url.searchParams.set('group_by', group);
        if (status) url.searchParams.set('status', status);
        else url.searchParams.delete('status');
        if (xaridor) url.searchParams.set('xaridor', xaridor);
        else url.searchParams.delete('xaridor');

        notificationsList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-spinner fa-spin"></i>
                <p>Yuklanmoqda...</p>
            </div>
        `;

        fetch(url, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            if (data.success) {
                notificationsList.innerHTML = data.html;
                document.querySelectorAll('.mark-btn').forEach(btn => {
                    btn.addEventListener('click', function() {
                        const id = this.dataset.id;
                        markAsNotified(id, this);
                    });
                });
            } else {
                showError('Ma\'lumotlarni yuklashda xatolik');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showError('Server bilan aloqa uzildi');
        });
    }

    filterButtons.forEach(button => {
        button.addEventListener('click', function() {
            filterButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            updateNotifications();
        });
    });

    sortSelect.addEventListener('change', updateNotifications);
    groupSelect.addEventListener('change', updateNotifications);
    statusFilter.addEventListener('change', updateNotifications);
    xaridorFilter.addEventListener('change', updateNotifications);

    function markAsNotified(id, button) {
        const originalHtml = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        button.disabled = true;

        fetch(`/chiqim/bildirishnoma/mark/${id}/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast('Bildirishnoma belgilandi', 'success');
                updateNotifications();
            } else {
                throw new Error(data.error || 'Xatolik yuz berdi');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast(error.message, 'error');
            button.innerHTML = originalHtml;
            button.disabled = false;
        });
    }

    function showError(message) {
        notificationsList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-exclamation-triangle"></i>
                <h3>Xatolik yuz berdi</h3>
                <p>${message}</p>
                <button class="btn btn-primary" onclick="location.reload()">
                    <i class="fas fa-sync-alt"></i> Qayta yuklash
                </button>
            </div>
        `;
    }

    function showToast(message, type) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('show');
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }, 10);
    }

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
});