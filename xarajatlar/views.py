from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.db import transaction
from .models import Xarajat
from .forms import XarajatForm
from trucks.models import Truck
import json
from datetime import datetime, timedelta
import logging

# Set up logging
logger = logging.getLogger(__name__)

@login_required
def xarajatlar_list(request):
    search_query = request.GET.get('search', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    if request.user.is_superuser:
        xarajatlar = Xarajat.objects.all().order_by('-date')
    else:
        xarajatlar = Xarajat.objects.filter(truck__user=request.user).order_by('-date')

    # Apply search filter
    if search_query:
        xarajatlar = xarajatlar.filter(
            Q(truck__po_id__icontains=search_query) |
            Q(truck__make__icontains=search_query) |
            Q(truck__model__icontains=search_query) |
            Q(expense_type__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Apply date range filter
    try:
        if start_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            xarajatlar = xarajatlar.filter(date__gte=start_date_obj)
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            xarajatlar = xarajatlar.filter(date__lte=end_date_obj)
    except ValueError:
        messages.error(request, "Invalid date format. Please use YYYY-MM-DD.")

    # Calculate serial numbers
    for index, xarajat in enumerate(xarajatlar, start=1):
        xarajat.serial_number = index

    total_xarajat = xarajatlar.aggregate(Sum('amount'))['amount__sum'] or 0
    form = XarajatForm()
    if not request.user.is_superuser:
        form.fields['truck'].queryset = Truck.objects.filter(user=request.user)

    context = {
        'xarajatlar': xarajatlar,
        'total_xarajat': total_xarajat,
        'form': form,
        'action': 'add',
        'search_query': search_query,
        'start_date': start_date,
        'end_date': end_date,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xarajat/xarajatlar_list.html', context, request=request)
        return JsonResponse({'success': True, 'html': html})

    return render(request, 'xarajat/xarajatlar_list.html', context)

@login_required
def xarajat_add(request):
    if request.method == 'POST':
        logger.info(f"Received POST request to add xarajat by user {request.user.username}")
        form = XarajatForm(request.POST, request.FILES)
        if form.is_valid():
            xarajat = form.save(commit=False)
            if not request.user.is_superuser and xarajat.truck.user != request.user:
                logger.warning(f"User {request.user.username} attempted to add expense for unauthorized truck {xarajat.truck.id}")
                return JsonResponse(
                    {'success': False, 'message': "You can only add expenses for your own trucks!"},
                    status=403)

            with transaction.atomic():
                time_window = timedelta(minutes=5)
                duplicate_check = Xarajat.objects.filter(
                    truck=xarajat.truck,
                    expense_type=xarajat.expense_type,
                    amount=xarajat.amount,
                    date__gte=xarajat.date - time_window,
                    date__lte=xarajat.date + time_window,
                    description=xarajat.description
                ).exists()

                if duplicate_check:
                    logger.warning(f"Duplicate expense detected for user {request.user.username}: {xarajat.truck}, {xarajat.expense_type}, {xarajat.amount}, {xarajat.date}")
                    return JsonResponse({
                        'success': False,
                        'message': "This expense appears to be a duplicate!",
                        'duplicate': True
                    }, status=400)

                xarajat.save()
                logger.info(f"Expense added successfully by user {request.user.username}: {xarajat.id}")

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': "Expense added successfully!",
                    'closeSidebar': True,
                    'reload': True
                })
            messages.success(request, "Expense added successfully!")
            return redirect('xarajatlar_list')
        else:
            logger.error(f"Form validation failed for user {request.user.username}: {form.errors.as_json()}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                errors = form.errors.as_json()
                return JsonResponse({
                    'success': False,
                    'errors': json.loads(errors),
                    'duplicate': False
                }, status=400)
    else:
        form = XarajatForm()
        if not request.user.is_superuser:
            form.fields['truck'].queryset = Truck.objects.filter(user=request.user)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            html = render_to_string('xarajat/xarajat_form.html', {
                'form': form,
                'action': 'add'
            }, request=request)
            return JsonResponse({'success': True, 'html': html})
        return render(request, 'xarajat/xarajat_form.html', {
            'form': form,
            'action': 'add'
        })

@login_required
def xarajat_edit(request, xarajat_id):
    if request.user.is_superuser:
        xarajat = get_object_or_404(Xarajat, id=xarajat_id)
    else:
        xarajat = get_object_or_404(Xarajat, id=xarajat_id, truck__user=request.user)

    if request.method == 'POST':
        logger.info(f"Received POST request to edit xarajat {xarajat_id} by user {request.user.username}")
        form = XarajatForm(request.POST, request.FILES, instance=xarajat)
        if form.is_valid():
            xarajat = form.save(commit=False)
            if not request.user.is_superuser and xarajat.truck.user != request.user:
                logger.warning(f"User {request.user.username} attempted to edit expense for unauthorized truck {xarajat.truck.id}")
                return JsonResponse(
                    {'success': False, 'message': "You can only edit expenses for your own trucks!"},
                    status=403)
            xarajat.save()
            logger.info(f"Expense {xarajat_id} updated successfully by user {request.user.username}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': "Expense updated successfully!",
                    'closeSidebar': True,
                    'reload': True
                })
            messages.success(request, "Expense updated successfully!")
            return redirect('xarajatlar_list')
        else:
            logger.error(f"Form validation failed for edit xarajat {xarajat_id} by user {request.user.username}: {form.errors.as_json()}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                errors = form.errors.as_json()
                return JsonResponse({'success': False, 'errors': json.loads(errors)}, status=400)

    form = XarajatForm(instance=xarajat)
    if not request.user.is_superuser:
        form.fields['truck'].queryset = Truck.objects.filter(user=request.user)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xarajat/xarajat_form.html', {
            'form': form,
            'action': 'edit',
            'xarajat_id': xarajat_id
        }, request=request)
        return JsonResponse({'success': True, 'html': html})

    return redirect('xarajatlar_list')

@login_required
def xarajat_delete(request, xarajat_id):
    if request.user.is_superuser:
        xarajat = get_object_or_404(Xarajat, id=xarajat_id)
    else:
        xarajat = get_object_or_404(Xarajat, id=xarajat_id, truck__user=request.user)

    if request.method == 'POST':
        logger.info(f"Received POST request to delete xarajat {xarajat_id} by user {request.user.username}")
        xarajat.delete()
        logger.info(f"Expense {xarajat_id} deleted successfully by user {request.user.username}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': "Expense deleted successfully!",
                'closeSidebar': True,
                'reload': True
            })
        messages.success(request, "Expense deleted successfully!")
        return redirect('xarajatlar_list')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xarajat/xarajat_delete.html', {
            'xarajat_id': xarajat_id,
            'xarajat': xarajat
        }, request=request)
        return JsonResponse({'success': True, 'html': html})

    return render(request, 'xarajat/xarajat_delete.html', {
        'xarajat_id': xarajat_id,
        'xarajat': xarajat
    })