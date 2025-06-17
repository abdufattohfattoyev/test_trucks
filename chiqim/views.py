from _decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.core.mail import send_mail
import calendar
from datetime import timedelta
import logging
from django.core.cache import cache
from .models import Bildirishnoma, Chiqim, BoshlangichTolov, TolovTuri, EmailHistory
from xaridorlar.models import Xaridor
from .forms import TolovForm, ChiqimForm, BoshlangichTolovForm
from trucks.models import Truck
from django.conf import settings

logger = logging.getLogger(__name__)

CACHE_TIMEOUT = 21600  # 6 hours

def create_bildirishnoma(chiqim, payment_date, days_before=30):
    Bildirishnoma.objects.update_or_create(
        chiqim=chiqim,
        tolov_sana=payment_date,
        defaults={'eslatma': False, 'eslatish_kunlari': int(days_before), 'email_sent': False}
    )

def update_notifications(chiqim):
    cache_key = f'notifications_chiqim_{chiqim.id}'
    cache.delete(cache_key)

    # Chiqim ma'lumotlarini yangilash
    chiqim = Chiqim.objects.prefetch_related('tolovlar', 'bildirishnomalar').get(id=chiqim.id)
    chiqim.update_totals()  # Qoldiq summa va oylik to'lovlarni yangilash

    if chiqim.qoldiq_summa <= 0:
        chiqim.bo_lib_tolov_muddat = 0
        chiqim.oyiga_tolov = 0
        chiqim.bildirishnomalar.all().delete()
        chiqim.save()
        cache.set(cache_key, {'status': 'cleared', 'notifications': []}, CACHE_TIMEOUT)
        return {'status': 'cleared', 'notifications': []}

    monthly_payment = chiqim.oyiga_tolov
    total_monthly_paid = chiqim.get_total_monthly_paid()
    total_months = chiqim.bo_lib_tolov_muddat
    start_date = chiqim.tolov_sana
    target_day = start_date.day
    current_date = timezone.now().date()

    payment_schedule = []
    existing_notifications = chiqim.bildirishnomalar.all()
    existing_dates = set(n.tolov_sana for n in existing_notifications)

    # To'lovlarni yig'ish
    monthly_payments = chiqim.tolovlar.all().order_by('sana')
    total_paid = sum(t.summa for t in monthly_payments)
    remaining_to_distribute = total_paid

    # Oylarga to'lovlarni taqsimlash
    payments_by_month = {}
    month_index = 0
    while remaining_to_distribute > 0 and month_index < total_months:
        next_month = start_date.month + month_index
        next_year = start_date.year + (next_month - 1) // 12
        next_month = (next_month - 1) % 12 + 1
        payment_month_key = start_date.replace(year=next_year, month=next_month, day=1)

        payment_amount = min(remaining_to_distribute, monthly_payment)
        payments_by_month[payment_month_key] = payment_amount
        remaining_to_distribute -= payment_amount
        logger.debug(f"Oy: {payment_month_key}, Taqsimlangan: {payment_amount}, Qoldi: {remaining_to_distribute}")
        month_index += 1

    # To'lov jadvalini yaratish va bildirishnomalarni yangilash
    for month in range(total_months):
        next_month = start_date.month + month
        next_year = start_date.year + (next_month - 1) // 12
        next_month = (next_month - 1) % 12 + 1
        last_day_of_month = calendar.monthrange(next_year, next_month)[1]
        payment_day = min(target_day, last_day_of_month)
        payment_date = start_date.replace(year=next_year, month=next_month, day=payment_day)
        payment_month_key = payment_date.replace(day=1)

        # Ushbu oy uchun to'langan summa
        paid_amount = payments_by_month.get(payment_month_key, Decimal('0'))
        is_paid = paid_amount >= monthly_payment
        logger.debug(
            f"Oy: {payment_month_key}, To'langan: {paid_amount}, Kerak: {monthly_payment}, To'landi: {is_paid}")

        # Qoldiq kunlar va kechikish kunlarini hisoblash
        days_left = (payment_date - current_date).days
        days_overdue = abs(days_left) if days_left < 0 else 0

        # Bildirishnoma yaratish yoki yangilash
        if not is_paid and payment_date not in existing_dates:
            Bildirishnoma.objects.create(
                chiqim=chiqim,
                tolov_sana=payment_date,
                eslatma=False,
                email_sent=False,
                eslatish_kunlari=30,
                status='pending' if days_left >= 0 else 'overdue',
                days_left=days_left,
                days_overdue=days_overdue
            )
            logger.debug(f"Yangi bildirishnoma yaratildi: Chiqim ID {chiqim.id}, Sana: {payment_date}")

        payment_schedule.append({
            'date': payment_date,
            'amount': float(monthly_payment),
            'paid_amount': float(paid_amount),
            'is_paid': is_paid,
            'days_left': days_left,
            'days_overdue': days_overdue
        })

    # Bildirishnomalarni yangilash
    notifications = chiqim.bildirishnomalar.all()
    for notification in notifications:
        notification_month = notification.tolov_sana.replace(day=1)
        paid_for_month = payments_by_month.get(notification_month, Decimal('0'))
        is_paid = paid_for_month >= monthly_payment or chiqim.qoldiq_summa <= 0
        days_left = (notification.tolov_sana - current_date).days
        days_overdue = abs(days_left) if days_left < 0 else 0

        logger.debug(
            f"Bildirishnoma ID {notification.id}, Oy: {notification_month}, To'langan: {paid_for_month}, Holat: {is_paid}, Qoldiq kunlar: {days_left}")

        if is_paid:
            notification.status = 'paid'
            notification.eslatma = True
        elif days_left < 0:
            notification.status = 'overdue'
        elif days_left <= 3:
            notification.status = 'urgent'
        elif days_left <= 7:
            notification.status = 'warning'
        else:
            notification.status = 'pending'

        notification.eslatma = days_left <= notification.eslatish_kunlari and not is_paid
        notification.days_left = days_left
        notification.days_overdue = days_overdue
        notification.save()

    # Keshni yangilash
    cached_data = {
        'status': 'updated',
        'notifications': [
            {
                'id': n.id,
                'tolov_sana': n.tolov_sana,
                'status': n.status,
                'eslatma': n.eslatma,
                'eslatish_kunlari': n.eslatish_kunlari,
                'days_left': n.days_left,
                'days_overdue': n.days_overdue,
                'email_sent': n.email_sent
            } for n in notifications
        ]
    }
    cache.set(cache_key, cached_data, CACHE_TIMEOUT)
    logger.debug(f"Kesh yangilandi: {cache_key}, Ma'lumot: {cached_data}")
    return cached_data


@login_required
def chiqim_list(request):
    logger.debug('Accessing chiqim_list view for user: %s', request.user.username)

    # Query data based on user permissions
    if request.user.is_superuser:
        chiqimlar = Chiqim.objects.all().select_related('truck', 'xaridor').prefetch_related('tolovlar',
                                                                                             'bildirishnomalar')
        trucks = Truck.objects.filter(sotilgan=False)
        xaridorlar = Xaridor.objects.all()
    else:
        chiqimlar = Chiqim.objects.filter(
            truck__user=request.user,
            xaridor__user=request.user
        ).select_related('truck', 'xaridor').prefetch_related('tolovlar', 'bildirishnomalar')
        trucks = Truck.objects.filter(user=request.user, sotilgan=False)
        xaridorlar = Xaridor.objects.filter(user=request.user)

    current_date = timezone.now().date()
    notification_days = 30
    tolov_forms = {}

    # Process chiqimlar in a single transaction to reduce database contention
    with transaction.atomic():
        for chiqim in chiqimlar:
            # Update totals without immediate save to defer database writes
            chiqim.update_totals(save=False)

            # Calculate payment totals
            total_boshlangich_paid = chiqim.get_total_boshlangich_paid()
            total_monthly_paid = chiqim.get_total_monthly_paid()
            remaining_debt = chiqim.qoldiq_summa

            # Build payment schedule
            payment_schedule = []
            start_date = chiqim.tolov_sana
            target_day = start_date.day
            monthly_payment = chiqim.oyiga_tolov
            total_months = chiqim.bo_lib_tolov_muddat
            paid_months = int(total_monthly_paid // monthly_payment) if monthly_payment > 0 else 0
            remaining_months = max(0, total_months - paid_months)

            for month in range(paid_months, total_months):
                next_month = start_date.month + month
                next_year = start_date.year + (next_month - 1) // 12
                next_month = (next_month - 1) % 12 + 1
                last_day_of_month = calendar.monthrange(next_year, next_month)[1]
                payment_day = min(target_day, last_day_of_month)
                payment_date = start_date.replace(year=next_year, month=next_month, day=payment_day)

                paid_amount = sum(
                    t.summa for t in chiqim.tolovlar.filter(
                        sana__year=payment_date.year,
                        sana__month=payment_date.month
                    )
                )
                is_paid = paid_amount >= monthly_payment
                days_left = (payment_date - current_date).days
                carryover = max(0, monthly_payment - paid_amount) if not is_paid else 0
                progress_percentage = ((chiqim.narx - remaining_debt) / chiqim.narx) * 100 if chiqim.narx > 0 else 0
                pending_debt = carryover if not is_paid and days_left >= 0 else 0

                payment_schedule.append({
                    'month': payment_date.strftime('%B %Y'),
                    'date': payment_date,
                    'amount': monthly_payment,
                    'paid_amount': paid_amount,
                    'is_paid': is_paid,
                    'days_left': days_left,
                    'carryover': carryover,
                    'progress_percentage': progress_percentage,
                    'pending_debt': pending_debt,
                    'debt_percentage': (remaining_debt / chiqim.narx) * 100 if chiqim.narx > 0 else 0
                })

            # Get next unpaid payment
            unpaid_notifications = chiqim.bildirishnomalar.filter(
                status__in=['pending', 'warning', 'urgent', 'overdue']
            ).order_by('tolov_sana')
            next_unpaid_payment = None
            if unpaid_notifications.exists():
                next_unpaid_notification = unpaid_notifications.first()
                days_left = (next_unpaid_notification.tolov_sana - current_date).days
                next_unpaid_payment = {
                    'date': next_unpaid_notification.tolov_sana,
                    'days_left': days_left,
                    'pending_debt': getattr(next_unpaid_notification, 'pending_debt', remaining_debt)
                }
            elif remaining_debt > 0 and payment_schedule:
                last_payment_date = payment_schedule[-1]['date']
                next_payment_month = last_payment_date.month + 1
                next_payment_year = last_payment_date.year + (next_payment_month - 1) // 12
                next_payment_month = (next_payment_month - 1) % 12 + 1
                last_day_of_month = calendar.monthrange(next_payment_year, next_payment_month)[1]
                next_payment_day = min(target_day, last_day_of_month)
                next_payment_date = last_payment_date.replace(
                    year=next_payment_year, month=next_payment_month, day=next_payment_day
                )
                days_left = (next_payment_date - current_date).days
                next_unpaid_payment = {
                    'date': next_payment_date,
                    'days_left': days_left,
                    'pending_debt': remaining_debt
                }

            # Set overdue notifications
            chiqim.overdue_notifications = list(
                chiqim.bildirishnomalar.filter(status='overdue').order_by('tolov_sana')
            )

            # Update chiqim attributes
            if next_unpaid_payment:
                days_until_payment = next_unpaid_payment['days_left']
                chiqim.next_payment_date = next_unpaid_payment['date']
                chiqim.days_until_payment = days_until_payment
                chiqim.days_overdue_display = abs(days_until_payment) if days_until_payment < 0 else 0
                chiqim.has_warning = days_until_payment <= notification_days
            else:
                chiqim.has_warning = False
                chiqim.next_payment_date = None
                chiqim.days_until_payment = None
                chiqim.days_overdue_display = 0

            chiqim.boshlangich_qoldiq = chiqim.get_boshlangich_qoldiq()

            # Save chiqim once after all updates
            chiqim.save()

            # Initialize tolov form
            tolov_forms[chiqim.id] = TolovForm(initial={'chiqim': chiqim})

    context = {
        'chiqimlar': chiqimlar,
        'trucks': trucks,
        'xaridorlar': xaridorlar,
        'now': timezone.now(),
        'tolov_forms': tolov_forms,
        'today': timezone.now().date(),
    }
    logger.debug('Rendering chiqim_list template with %d chiqimlar', len(chiqimlar))
    return render(request, 'chiqim/chiqim_list.html', context)

@login_required
def chiqim_detail(request, id):
    logger.debug(f'Accessing chiqim_detail view for Chiqim ID {id} by user {request.user}')
    chiqim = get_object_or_404(
        Chiqim.objects.select_related('truck', 'xaridor').prefetch_related('tolovlar', 'boshlangich_tolovlar', 'bildirishnomalar'),
        id=id
    )

    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        logger.warning(f'Unauthorized access attempt by user {request.user} for Chiqim ID {id}')
        return JsonResponse(
            {'success': False, 'error': "Sizga bu chiqimni ko'rishga ruxsat yo'q!"},
            status=403
        )

    payment_schedule = []
    total_boshlangich_paid = chiqim.get_total_boshlangich_paid()
    total_monthly_paid = chiqim.get_total_monthly_paid()
    remaining_debt = chiqim.qoldiq_summa
    boshlangich_qoldiq = chiqim.get_boshlangich_qoldiq()
    current_date = timezone.now().date()

    if chiqim.qoldiq_summa <= 0:
        chiqim.bo_lib_tolov_muddat = 0
        chiqim.oyiga_tolov = Decimal('0')
        chiqim.bildirishnomalar.all().delete()
        chiqim.save()
        cache.delete(f'notifications_chiqim_{chiqim.id}')
    elif chiqim.bo_lib_tolov_muddat > 0:
        monthly_payment = chiqim.oyiga_tolov or Decimal('0')  # Fallback to 0 if None
        start_date = chiqim.tolov_sana or current_date

        if start_date == current_date:
            next_month = start_date.month + 1
            next_year = start_date.year + (next_month - 1) // 12
            next_month = (next_month - 1) % 12 + 1
            last_day_of_month = calendar.monthrange(next_year, next_month)[1]
            payment_day = min(start_date.day, last_day_of_month)
            start_date = start_date.replace(year=next_year, month=next_month, day=payment_day)

        target_day = start_date.day
        remaining_to_distribute = total_monthly_paid
        accumulated_paid = total_boshlangich_paid
        carryover_amount = Decimal('0')

        for month in range(chiqim.bo_lib_tolov_muddat):
            next_month = start_date.month + month
            next_year = start_date.year + (next_month - 1) // 12
            next_month = (next_month - 1) % 12 + 1
            last_day_of_month = calendar.monthrange(next_year, next_month)[1]
            payment_day = min(target_day, last_day_of_month)
            payment_date = start_date.replace(year=next_year, month=next_month, day=payment_day)

            paid_amount_for_month = Decimal('0')
            is_paid = False

            if monthly_payment > 0 and remaining_to_distribute >= monthly_payment:
                paid_amount_for_month = monthly_payment
                remaining_to_distribute -= monthly_payment
                is_paid = True
                carryover_amount = remaining_to_distribute
            elif monthly_payment > 0 and remaining_to_distribute > 0:
                paid_amount_for_month = remaining_to_distribute
                remaining_to_distribute = Decimal('0')
                carryover_amount = Decimal('0')
                is_paid = False
            else:
                paid_amount_for_month = Decimal('0')
                carryover_amount = Decimal('0')
                is_paid = False

            accumulated_paid += paid_amount_for_month
            remaining_debt = max(Decimal('0'), chiqim.narx - accumulated_paid)
            progress_percentage = (paid_amount_for_month / monthly_payment * 100) if monthly_payment > 0 else Decimal('0')

            payment_schedule.append({
                'month': f"{next_month:02d}/{next_year}",
                'date': payment_date,
                'amount': float(monthly_payment),
                'paid_amount': float(paid_amount_for_month),
                'is_paid': is_paid,
                'days_left': max(0, (payment_date - current_date).days),
                'carryover': float(carryover_amount),
                'adjusted_payment': float(monthly_payment - paid_amount_for_month) if not is_paid else 0,
                'debt_percentage': float((remaining_debt / chiqim.narx * 100)) if chiqim.narx > 0 else 0,
                'progress_percentage': float(progress_percentage),
                'pending_debt': float(monthly_payment - paid_amount_for_month) if not is_paid else 0,
            })

    context = {
        'chiqim': chiqim,
        'payment_schedule': payment_schedule,
        'total_boshlangich_paid': float(total_boshlangich_paid),
        'total_monthly_paid': float(total_monthly_paid),
        'boshlangich_qoldiq': float(boshlangich_qoldiq),
        'remaining_debt': float(remaining_debt),
        'current_date': current_date,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            html = render_to_string('chiqim/chiqim_detail.html', context, request=request)
            return JsonResponse({'success': True, 'html': html})
        except Exception as e:
            logger.error(f'Error rendering AJAX response for Chiqim ID {id}: {str(e)}')
            return JsonResponse({'success': False, 'error': 'Ichki server xatosi'}, status=500)

    return render(request, 'chiqim/chiqim_detail.html', context)

@login_required
def chiqim_create(request):
    if request.method == 'POST':
        form = ChiqimForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    chiqim = form.save(commit=False)
                    chiqim.tolov_sana = form.cleaned_data['tolov_sana']  # Sana aniq o'rnatiladi
                    if request.FILES.get('hujjatlar'):
                        chiqim.hujjatlar = request.FILES['hujjatlar']
                        chiqim.original_file_name = request.FILES['hujjatlar'].name
                    chiqim.save()
                    logger.info(f"New expense created: ID={chiqim.id}, User={request.user.username}, Tolov_sana={chiqim.tolov_sana}")
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': "Chiqim muvaffaqiyatli qo'shildi!",
                            'redirect_url': None
                        })
                    return redirect('chiqim_list')
            except Exception as e:
                logger.error(f"Error saving expense: {str(e)}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'errors': {'__all__': ['Kutilmagan xatolik yuz berdi. Iltimos, qayta urinib ko\'ring.']},
                    }, status=500)
                raise
        else:
            logger.warning(f"Form validation failed: {form.errors.as_json()}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                errors = {field: [error['message'] for error in errors] for field, errors in form.errors.as_data().items()}
                return JsonResponse({
                    'success': False,
                    'errors': errors,
                }, status=400)
    else:
        form = ChiqimForm(user=request.user)
    context = {
        'form': form,
        'today': timezone.now().date(),
    }
    return render(request, 'chiqim/chiqim_form.html', context)

@login_required
def chiqim_update(request, id):
    chiqim = get_object_or_404(Chiqim, id=id)
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': 'Sizga bu chiqimni tahrirlashga ruxsat yo\'q!'}, status=403)

    if request.method == 'POST':
        form = ChiqimForm(request.POST, request.FILES, instance=chiqim, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    chiqim = form.save(commit=False)
                    chiqim.tolov_sana = form.cleaned_data['tolov_sana']  # Sana aniq o'rnatiladi
                    if request.FILES.get('hujjatlar'):
                        chiqim.hujjatlar = request.FILES['hujjatlar']
                        chiqim.original_file_name = request.FILES['hujjatlar'].name
                    chiqim.save()
                    chiqim.bildirishnomalar.all().delete()
                    cache.delete(f'notifications_chiqim_{chiqim.id}')
                    update_notifications(chiqim)
                    logger.info(f"Expense updated: ID={chiqim.id}, User={request.user.username}, Tolov_sana={chiqim.tolov_sana}")
                    return JsonResponse({'success': True, 'message': 'Chiqim muvaffaqiyatli yangilandi!', 'reload': True})
            except Exception as e:
                logger.error(f"Error updating expense: {str(e)}")
                return JsonResponse({'success': False, 'error': 'Chiqimni yangilashda xatolik yuz berdi!'}, status=500)
        else:
            errors = {field: [str(error) for error in errors] for field, errors in form.errors.items()}
            logger.warning(f'Form errors: {errors}')
            return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = ChiqimForm(instance=chiqim, user=request.user)
        context = {
            'form': form,
            'chiqim': chiqim,
            'trucks': Truck.objects.filter(user=request.user, sotilgan=False) if not request.user.is_superuser else Truck.objects.filter(sotilgan=False),
            'xaridorlar': Xaridor.objects.filter(user=request.user) if not request.user.is_superuser else Xaridor.objects.all(),
        }
        return render(request, 'chiqim/chiqim_form.html', context)

@login_required
def chiqim_delete(request, id):
    chiqim = get_object_or_404(Chiqim, id=id)
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': "Sizga bu chiqimni o'chirishga ruxsat yo'q!"}, status=403)

    if request.method in ['POST', 'DELETE']:
        try:
            with transaction.atomic():
                old_truck = chiqim.truck
                chiqim.bildirishnomalar.all().delete()
                cache.delete(f'notifications_chiqim_{chiqim.id}')
                chiqim.delete()
                old_truck.sotilgan = False
                old_truck.save()
                logger.info(f'Chiqim deleted: ID {id}, truck {old_truck.id} marked unsold')
                return JsonResponse({'success': True, 'message': "Chiqim muvaffaqiyatli o'chirildi!", 'reload': True})
        except Exception as e:
            logger.error(f'Error deleting Chiqim ID {id}: {str(e)}')
            return JsonResponse({'success': False, 'error': "Chiqimni o'chirishda xatolik yuz berdi!"}, status=500)
    else:
        return render(request, 'chiqim/chiqim_delete_form.html', {'chiqim': chiqim})

@login_required
def add_boshlangich_payment(request, chiqim_id):
    chiqim = get_object_or_404(Chiqim, id=chiqim_id)
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse(
            {'success': False, 'error': "Sizga bu chiqim uchun boshlang'ich to'lov qo'shishga ruxsat yo'q!"},
            status=403
        )

    if request.method == 'POST':
        form = BoshlangichTolovForm(request.POST, initial={'chiqim': chiqim})
        if form.is_valid():
            tolov = form.save(commit=False)
            tolov.chiqim = chiqim
            tolov.xaridor = chiqim.xaridor
            tolov.sana = form.cleaned_data['sana'] or timezone.now().date()
            tolov.save()
            chiqim.update_totals()
            chiqim.save()
            cache.delete(f'notifications_chiqim_{chiqim.id}')
            update_notifications(chiqim)
            return JsonResponse({
                'success': True,
                'message': "Boshlang'ich to'lov muvaffaqiyatli qo'shildi!",
                'reload': True,
                'boshlangich_qoldiq': float(chiqim.get_boshlangich_qoldiq()),
                'tolov_summa': float(tolov.summa)
            })
        else:
            errors = {field: [str(error) for error in errors] for field, errors in form.errors.items()}
            logger.warning(f'Initial payment form errors: {errors}')
            return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = BoshlangichTolovForm(initial={'chiqim': chiqim})
        context = {
            'form': form,
            'chiqim': chiqim,
            'today': timezone.now().date(),
        }
        return render(request, 'chiqim/boshlangich_tolov_form.html', context)

@login_required
def update_boshlangich_payment(request, tolov_id):
    tolov = get_object_or_404(BoshlangichTolov, id=tolov_id)
    chiqim = tolov.chiqim
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': "Sizga bu boshlang'ich to'lovni tahrirlashga ruxsat yo'q!"}, status=403)

    if request.method == 'POST':
        form = BoshlangichTolovForm(request.POST, instance=tolov, initial={'chiqim': chiqim})
        if form.is_valid():
            tolov = form.save()
            chiqim.update_totals()
            chiqim.save()
            cache.delete(f'notifications_chiqim_{chiqim.id}')
            update_notifications(chiqim)
            return JsonResponse({
                'success': True,
                'message': "Boshlang'ich to'lov muvaffaqiyatli yangilandi!",
                'reload': True,
                'boshlangich_qoldiq': float(chiqim.get_boshlangich_qoldiq()),
                'tolov_summa': float(tolov.summa)
            })
        else:
            errors = {field: [str(error) for error in errors] for field, errors in form.errors.items()}
            logger.warning(f'Initial payment update form errors: {errors}')
            return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = BoshlangichTolovForm(instance=tolov, initial={'chiqim': chiqim})
        return render(request, 'chiqim/boshlangich_tolov_form.html', {'form': form, 'chiqim': chiqim, 'tolov': tolov})

@login_required
def delete_boshlangich_payment(request, tolov_id):
    tolov = get_object_or_404(BoshlangichTolov, id=tolov_id)
    chiqim = tolov.chiqim
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': "Sizga bu boshlang'ich to'lovni o'chirishga ruxsat yo'q!"}, status=403)

    if request.method == 'POST':
        tolov.delete()
        chiqim.update_totals()
        chiqim.save()
        cache.delete(f'notifications_chiqim_{chiqim.id}')
        update_notifications(chiqim)
        return JsonResponse({
            'success': True,
            'message': "Boshlang'ich to'lov muvaffaqiyatli o'chirildi!",
            'reload': True,
            'boshlangich_qoldiq': float(chiqim.get_boshlangich_qoldiq())
        })
    else:
        return render(request, 'chiqim/boshlangich_tolov_delete_form.html', {'tolov': tolov, 'chiqim': chiqim})

@login_required
def add_payment(request, chiqim_id):
    chiqim = get_object_or_404(Chiqim, id=chiqim_id)
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse(
            {'success': False, 'error': "Sizga bu chiqim uchun to'lov qo'shishga ruxsat yo'q!"},
            status=403
        )

    if request.method == 'POST':
        form = TolovForm(request.POST, initial={'chiqim': chiqim})
        if form.is_valid():
            with transaction.atomic():
                tolov = form.save(commit=False)
                tolov.chiqim = chiqim
                tolov.xaridor = chiqim.xaridor
                tolov.sana = form.cleaned_data['sana'] or timezone.now().date()
                tolov.save()
                chiqim.update_totals()
                chiqim.save()
                cache.delete(f'notifications_chiqim_{chiqim.id}')
                update_notifications(chiqim)
                return JsonResponse({
                    'success': True,
                    'message': "To'lov muvaffaqiyatli qo'shildi!",
                    'reload': True,
                    'remaining_debt': float(chiqim.qoldiq_summa),
                    'tolov_summa': float(tolov.summa)
                })
        else:
            errors = {field: [str(error) for error in errors] for field, errors in form.errors.items()}
            logger.warning(f'Payment form errors: {errors}')
            main_error = errors.get('summa', ['Unknown error'])[0] if 'summa' in errors else 'Formani tekshiring'
            return JsonResponse({
                'success': False,
                'error': main_error,
                'errors': errors
            }, status=400)
    else:
        form = TolovForm(initial={'chiqim': chiqim})
        context = {
            'form': form,
            'chiqim': chiqim,
            'today': timezone.now().date(),
        }
        return render(request, 'chiqim/tolov_form.html', context)

@login_required
def update_payment(request, tolov_id):
    tolov = get_object_or_404(TolovTuri, id=tolov_id)
    chiqim = tolov.chiqim
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': "Sizga bu to'lovni tahrirlashga ruxsat yo'q!"}, status=403)

    if request.method == 'POST':
        form = TolovForm(request.POST, instance=tolov, initial={'chiqim': chiqim})
        if form.is_valid():
            tolov = form.save()
            chiqim.update_totals()
            chiqim.save()
            cache.delete(f'notifications_chiqim_{chiqim.id}')
            update_notifications(chiqim)
            return JsonResponse({
                'success': True,
                'message': "To'lov muvaffaqiyatli yangilandi!",
                'reload': True
            })
        else:
            errors = {field: [str(error) for error in errors] for field, errors in form.errors.items()}
            logger.warning(f'Payment update form errors: {errors}')
            return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = TolovForm(instance=tolov, initial={'chiqim': chiqim})
        return render(request, 'chiqim/tolov_form.html', {'form': form, 'chiqim': chiqim, 'tolov': tolov})

@login_required
def delete_payment(request, tolov_id):
    tolov = get_object_or_404(TolovTuri, id=tolov_id)
    chiqim = tolov.chiqim
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': "Sizga bu to'lovni o'chirishga ruxsat yo'q!"}, status=403)

    if request.method == 'POST':
        tolov.delete()
        chiqim.update_totals()
        chiqim.save()
        cache.delete(f'notifications_chiqim_{chiqim.id}')
        update_notifications(chiqim)
        return JsonResponse({
            'success': True,
            'message': "To'lov muvaffaqiyatli o'chirildi!",
            'reload': True
        })
    else:
        return render(request, 'chiqim/tolov_delete_form.html', {'tolov': tolov, 'chiqim': chiqim})

@login_required
def bildirisnoma_list(request):
    logger.debug('Accessing bildirisnoma_list view')
    current_date = timezone.now().date()

    days_filter = request.GET.get('days', '0')
    sort_by = request.GET.get('sort', 'days_left')
    page = request.GET.get('page', '1')

    try:
        days = int(days_filter)
        if days not in [0, 1, 5, 7, 30]:
            days = 0
    except ValueError:
        days = 0

    if request.user.is_superuser:
        chiqimlar = Chiqim.objects.filter(qoldiq_summa__gt=0).select_related('xaridor', 'truck')
    else:
        chiqimlar = Chiqim.objects.filter(
            truck__user=request.user,
            xaridor__user=request.user,
            qoldiq_summa__gt=0
        ).select_related('xaridor', 'truck')

    bildirisnomalar = []
    for chiqim in chiqimlar:
        chiqim.update_totals()
        cached_data = update_notifications(chiqim)
        unpaid_notifications = [
            n for n in cached_data['notifications']
            if n['status'] in ['pending', 'warning', 'urgent', 'overdue']
        ]

        if unpaid_notifications:
            first_unpaid = min(unpaid_notifications, key=lambda x: x['tolov_sana'])
            bildirisnoma = Bildirishnoma.objects.get(id=first_unpaid['id'])
            days_left = first_unpaid['days_left']
            days_overdue = first_unpaid['days_overdue']

            if days == 0 or (days_left <= days and days_left >= 0) or (days_left < 0 and days == 0):
                bildirisnoma.custom_days_left = days_left
                bildirisnoma.abs_days_left = days_overdue
                bildirisnomalar.append(bildirisnoma)
        else:
            logger.debug(f"No unpaid notifications for Chiqim ID {chiqim.id}")

    # Tartiblash
    if sort_by == 'customer':
        bildirisnomalar = sorted(bildirisnomalar, key=lambda x: x.chiqim.xaridor.ism_familiya)
    else:
        bildirisnomalar = sorted(bildirisnomalar, key=lambda x: x.tolov_sana)

    # Sahifalash
    paginator = Paginator(bildirisnomalar, 10)
    try:
        page_obj = paginator.page(page)
    except Exception:
        page_obj = paginator.page(1)

    notification_count = sum(1 for b in bildirisnomalar if b.tolov_sana <= current_date + timedelta(days=5) and b.status in ['warning', 'urgent', 'overdue'])

    context = {
        'bildirisnomalar': page_obj,
        'current_filter': days_filter,
        'current_sort': sort_by,
        'page_obj': page_obj,
        'paginator': paginator,
        'notification_count': notification_count,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            html = render_to_string('chiqim/bildirishnoma_list_partial.html', context, request=request)
            return JsonResponse({
                'html': html,
                'current_page': page_obj.number,
                'num_pages': paginator.num_pages,
                'notification_count': notification_count,
            })
        except Exception as e:
            logger.error(f'Error rendering AJAX response: {str(e)}')
            return JsonResponse({'success': False, 'error': 'Ichki server xatosi'}, status=500)

    return render(request, 'chiqim/bildirishnomalar.html', context)

@login_required
def mark_notification(request, bildirishnoma_id):
    if request.method == 'POST':
        bildirisnoma = get_object_or_404(Bildirishnoma, id=bildirishnoma_id)
        if not request.user.is_superuser and (bildirisnoma.chiqim.truck.user != request.user or bildirisnoma.chiqim.xaridor.user != request.user):
            logger.warning(f'Unauthorized attempt to mark notification ID {bildirishnoma_id} by user {request.user}')
            return JsonResponse({'success': False, 'error': 'Sizga bu bildirisnomani o\'zgartirishga ruxsat yo\'q!'}, status=403)
        if bildirisnoma.eslatma:
            return JsonResponse({'success': False, 'error': 'Bu bildirisnoma allaqachon belgilangan!'}, status=400)
        bildirisnoma.eslatma = True
        bildirisnoma.save()
        cache.delete(f'notifications_chiqim_{bildirisnoma.chiqim.id}')
        logger.info(f'Notification marked as notified: ID {bildirishnoma_id}')
        return JsonResponse({'success': True, 'message': 'Bildirisnoma muvaffaqiyatli belgilandi!'})
    return JsonResponse({'success': False, 'error': 'Faqat POST so\'rovlari qabul qilinadi'}, status=400)

@login_required
def send_payment_reminder_email(request, bildirishnoma_id):
    if request.method != 'POST':
        logger.error(f"Invalid request method for bildirisnoma_id {bildirishnoma_id}")
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    try:
        bildirishnoma = Bildirishnoma.objects.get(id=bildirishnoma_id)
        logger.info(f"Processing notification ID {bildirishnoma_id}")
        chiqim = bildirishnoma.chiqim
        xaridor = chiqim.xaridor

        days_left = bildirishnoma.days_left or 0
        force_resend = request.POST.get('force_resend', 'false').lower() == 'true'
        if days_left > 5 and not force_resend and bildirishnoma.email_sent:
            logger.warning(f"Email already sent for ID {bildirishnoma_id}, days_left: {days_left}")
            return JsonResponse({'error': 'Email already sent and more than 5 days left'}, status=400)

        subject = f"Payment Reminder for {chiqim.truck.make} {chiqim.truck.model}"
        message = (
            f"Assalomu alaykum, {xaridor.ism_familiya},\n\n"
            f"Sizning {chiqim.truck.make} {chiqim.truck.model} uchun to'lov muddati yaqinlashmoqda.\n"
            f"To'lov summasi: ${chiqim.oyiga_tolov:,.2f}\n"
            f"To'lov sanasi: {bildirishnoma.tolov_sana}\n"
            f"Qoldiq summa: ${chiqim.qoldiq_summa:,.2f}\n\n"
            f"Iltimos, to'lovni o'z vaqtida amalga oshiring.\n"
            f"Rahmat!"
        )
        recipient_list = [xaridor.email]

        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_list,
                fail_silently=False,
            )
            # Email tarixini saqlash
            EmailHistory.objects.create(
                bildirishnoma=bildirishnoma,
                subject=subject,
                message=message,
                recipient=xaridor.email,
                status='success'
            )
            bildirishnoma.email_sent = True
            bildirishnoma.save()
            logger.info(f"Email sent successfully for ID {bildirishnoma_id}")
            return JsonResponse({'success': True, 'message': 'Email sent successfully'})

        except Exception as e:
            # Xato bo'lsa, tarixni xato sifatida saqlash
            EmailHistory.objects.create(
                bildirishnoma=bildirishnoma,
                subject=subject,
                message=message,
                recipient=xaridor.email,
                status='failed',
                error_message=str(e)
            )
            logger.error(f"Error sending email for ID {bildirishnoma_id}: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)

    except Bildirishnoma.DoesNotExist:
        logger.error(f"Notification not found for ID {bildirishnoma_id}")
        return JsonResponse({'error': 'Notification not found'}, status=404)

@login_required
def email_history(request, bildirishnoma_id):
    bildirishnoma = get_object_or_404(Bildirishnoma, id=bildirishnoma_id)
    if not request.user.is_superuser and (bildirishnoma.chiqim.truck.user != request.user or bildirishnoma.chiqim.xaridor.user != request.user):
        logger.warning(f'Unauthorized attempt to view email history for notification ID {bildirishnoma_id} by user {request.user}')
        return JsonResponse({'success': False, 'error': 'Sizga bu email tarixini ko\'rishga ruxsat yo\'q!'}, status=403)

    email_history = bildirishnoma.email_history.all()
    context = {
        'email_history': email_history,
        'bildirishnoma': bildirishnoma,
        'chiqim': bildirishnoma.chiqim,
        'xaridor': bildirishnoma.chiqim.xaridor,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            html = render_to_string('chiqim/email_history.html', context, request=request)
            return JsonResponse({'success': True, 'html': html})
        except Exception as e:
            logger.error(f'Error rendering email history for notification ID {bildirishnoma_id}: {str(e)}')
            return JsonResponse({'success': False, 'error': 'Ichki server xatosi'}, status=500)

    return render(request, 'chiqim/email_history.html', context)


@login_required
def email_statistics(request):
    total_emails = EmailHistory.objects.count()
    successful_emails = EmailHistory.objects.filter(status='success').count()
    failed_emails = EmailHistory.objects.filter(status='failed').count()

    return JsonResponse({
        'total': total_emails,
        'successful': successful_emails,
        'failed': failed_emails
    })