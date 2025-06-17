from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.db import models
from django.core.paginator import Paginator
from .models import Qarz, Payment
from .forms import QarzForm, PaymentForm
from trucks.models import Truck


@login_required
def qarz_view(request, action=None, qarz_id=None, truck_id=None, payment_id=None):
    """Main view for handling loans"""
    # Fetch loans where the user is the lender
    user_loans = Qarz.objects.filter(lender=request.user).select_related('lender', 'truck').prefetch_related('payments')

    # Truck details
    if action == 'truck_details' and truck_id:
        truck = get_object_or_404(Truck, id=truck_id, user=request.user)
        context = {'section': 'truck_details', 'truck': truck}
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            html = render_to_string('qarz/qarz.html', context, request=request)
            return JsonResponse({'html': html})
        return render(request, 'qarz/qarz.html', context)

    # Loan details
    if action == 'detail' and qarz_id:
        qarz = get_object_or_404(Qarz, id=qarz_id)
        if request.user != qarz.lender:
            return JsonResponse({'error': "Permission denied"}, status=403)
        context = {'section': 'detail', 'qarz': qarz}
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            html = render_to_string('qarz/qarz.html', context, request=request)
            return JsonResponse({'html': html, 'qarz_amount': float(qarz.amount)})
        return render(request, 'qarz/qarz.html', context)

    # Loan list
    if action is None:
        total_remaining_amount = user_loans.aggregate(total=models.Sum('remaining_amount'))['total'] or 0
        active_loans = user_loans.filter(is_paid=False)
        paid_loans = user_loans.filter(is_paid=True)
        last_payment = Payment.objects.filter(qarz__in=user_loans).order_by('-payment_date').first()
        last_payment_amount = last_payment.amount if last_payment else 0
        last_payment_date = last_payment.payment_date if last_payment else None
        total_loans = user_loans.count() or 1
        total_remaining_percentage = min((total_remaining_amount / (total_remaining_amount + 1)) * 100, 100) if total_remaining_amount else 0
        active_loan_count = active_loans.count()
        paid_loan_count = paid_loans.count()

        paginator = Paginator(user_loans, 9)
        page_number = request.GET.get('page')
        loans = paginator.get_page(page_number)

        context = {
            'section': 'list',
            'qarzlar': loans,
            'total_remaining_amount': total_remaining_amount,
            'total_remaining_percentage': total_remaining_percentage,
            'active_loan_count': active_loan_count,
            'paid_loan_count': paid_loan_count,
            'last_payment_amount': last_payment_amount,
            'last_payment_date': last_payment_date,
        }

    # Add or update loan
    if action in ['add', 'update']:
        qarz = get_object_or_404(Qarz, id=qarz_id) if action == 'update' and qarz_id else None
        if qarz and request.user != qarz.lender:
            messages.error(request, "Only the lender can edit this loan!")
            return redirect('qarz_view')

        if request.method == 'POST':
            form = QarzForm(request.POST, instance=qarz, user=request.user)
            if form.is_valid():
                qarz_instance = form.save(commit=False)
                if action == 'add':
                    qarz_instance.lender = request.user  # Set lender to logged-in user
                    qarz_instance.remaining_amount = qarz_instance.amount
                else:
                    total_payments = qarz_instance.payments.aggregate(total=models.Sum('amount'))['total'] or 0
                    qarz_instance.remaining_amount = qarz_instance.amount - total_payments
                    qarz_instance.is_paid = qarz_instance.remaining_amount <= 0
                    if qarz_instance.is_paid:
                        qarz_instance.remaining_amount = 0
                qarz_instance.save()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    context = {'section': 'detail', 'qarz': qarz_instance}
                    html = render_to_string('qarz/qarz.html', context, request=request)
                    detail_html = render_to_string('qarz/qarz_detail.html', context, request=request)
                    return JsonResponse({
                        'success': True,
                        'message': f"Loan successfully {'updated' if qarz_id else 'created'}!",
                        'html': html,
                        'detail_html': detail_html,
                        'qarz_amount': float(qarz_instance.amount),
                        'remaining_amount': float(qarz_instance.remaining_amount),
                        'is_paid': qarz_instance.is_paid,
                        'paid_amount': float(qarz_instance.get_paid_amount()),
                        'percentage_paid': qarz_instance.percentage_paid
                    })
                messages.success(request, f"Loan successfully {'updated' if qarz_id else 'created'}!")
                return redirect('qarz_view')
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'errors': form.errors})
                messages.error(request, "Error in form submission.")
        else:
            form = QarzForm(instance=qarz, user=request.user)
        context = {'section': 'form', 'form': form, 'qarz': qarz}

    # Delete loan
    elif action == 'delete' and qarz_id:
        qarz = get_object_or_404(Qarz, id=qarz_id)
        if request.user != qarz.lender:
            messages.error(request, "Only the lender can delete this loan!")
            return redirect('qarz_view')

        if request.method == 'POST':
            qarz.delete()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'Loan successfully deleted!', 'reload': True})
            messages.success(request, "Loan successfully deleted!")
            return redirect('qarz_view')
        context = {'section': 'delete', 'qarz': qarz}

    # Add payment
    elif action == 'add_payment' and qarz_id:
        qarz = get_object_or_404(Qarz, id=qarz_id)
        if request.user != qarz.lender:
            messages.error(request, "Only the lender can add a payment!")
            return redirect('qarz_view')

        if qarz.is_paid:
            messages.error(request, "This loan is already fully paid!")
            return redirect('qarz_view')

        if request.method == 'POST':
            payment_form = PaymentForm(request.POST)
            if payment_form.is_valid():
                payment = payment_form.save(commit=False)
                payment.qarz = qarz
                payment.save()
                total_payments = qarz.payments.aggregate(total=models.Sum('amount'))['total'] or 0
                qarz.remaining_amount = qarz.amount - total_payments
                qarz.is_paid = qarz.remaining_amount <= 0
                if qarz.is_paid:
                    qarz.remaining_amount = 0
                qarz.save()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    context = {'section': 'detail', 'qarz': qarz}
                    html = render_to_string('qarz/qarz.html', context, request=request)
                    detail_html = render_to_string('qarz/qarz_detail.html', context, request=request)
                    return JsonResponse({
                        'success': True,
                        'message': f"Payment of ${payment.amount} added successfully!",
                        'html': html,
                        'detail_html': detail_html,
                        'qarz_amount': float(qarz.amount),
                        'remaining_amount': float(qarz.remaining_amount),
                        'is_paid': qarz.is_paid,
                        'paid_amount': float(qarz.get_paid_amount()),
                        'percentage_paid': qarz.percentage_paid
                    })
                messages.success(request, f"Payment of ${payment.amount} added successfully!")
                return redirect('qarz_view')
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'errors': payment_form.errors})
                messages.error(request, "Error adding payment.")
        else:
            payment_form = PaymentForm()
        context = {'section': 'add_payment', 'qarz': qarz, 'payment_form': payment_form}

    # Update payment
    elif action == 'update_payment' and qarz_id and payment_id:
        qarz = get_object_or_404(Qarz, id=qarz_id)
        payment = get_object_or_404(Payment, id=payment_id, qarz=qarz)
        if request.user != qarz.lender:
            return JsonResponse({'success': False, 'message': "Only the lender can edit this payment!"}, status=403)

        if request.method == 'POST':
            payment_form = PaymentForm(request.POST, instance=payment)
            if payment_form.is_valid():
                payment_form.save()
                total_payments = qarz.payments.aggregate(total=models.Sum('amount'))['total'] or 0
                qarz.remaining_amount = qarz.amount - total_payments
                qarz.is_paid = qarz.remaining_amount <= 0
                if qarz.is_paid:
                    qarz.remaining_amount = 0
                qarz.save()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    context = {'section': 'detail', 'qarz': qarz}
                    html = render_to_string('qarz/qarz.html', context, request=request)
                    detail_html = render_to_string('qarz/qarz_detail.html', context, request=request)
                    return JsonResponse({
                        'success': True,
                        'message': "Payment updated successfully!",
                        'html': html,
                        'detail_html': detail_html,
                        'qarz_amount': float(qarz.amount),
                        'remaining_amount': float(qarz.remaining_amount),
                        'is_paid': qarz.is_paid,
                        'paid_amount': float(qarz.get_paid_amount()),
                        'percentage_paid': qarz.percentage_paid
                    })
                messages.success(request, "Payment updated successfully!")
                return redirect('qarz_view')
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'errors': payment_form.errors})
                messages.error(request, "Error updating payment.")
        else:
            payment_form = PaymentForm(instance=payment)
        context = {'section': 'update_payment', 'qarz': qarz, 'payment_form': payment_form, 'payment': payment}

    # Delete payment
    elif action == 'delete_payment' and qarz_id and payment_id:
        qarz = get_object_or_404(Qarz, id=qarz_id)
        payment = get_object_or_404(Payment, id=payment_id, qarz=qarz)
        if request.user != qarz.lender:
            return JsonResponse({'success': False, 'message': "Only the lender can delete this payment!"}, status=403)

        if request.method in ['POST', 'DELETE']:
            payment.delete()
            total_payments = qarz.payments.aggregate(total=models.Sum('amount'))['total'] or 0
            qarz.remaining_amount = qarz.amount - total_payments
            qarz.is_paid = qarz.remaining_amount <= 0
            if qarz.is_paid:
                qarz.remaining_amount = 0
            qarz.save()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                context = {'section': 'detail', 'qarz': qarz}
                html = render_to_string('qarz/qarz.html', context, request=request)
                detail_html = render_to_string('qarz/qarz_detail.html', context, request=request)
                return JsonResponse({
                    'success': True,
                    'message': 'Payment deleted successfully!',
                    'html': html,
                    'detail_html': detail_html,
                    'qarz_amount': float(qarz.amount),
                    'remaining_amount': float(qarz.remaining_amount),
                    'is_paid': qarz.is_paid,
                    'paid_amount': float(qarz.get_paid_amount()),
                    'percentage_paid': qarz.percentage_paid
                })
            messages.success(request, "Payment deleted successfully!")
            return redirect('qarz_view')
        context = {'section': 'delete_payment', 'qarz': qarz, 'payment': payment}

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and 'context' in locals():
        html = render_to_string('qarz/qarz.html', context, request=request)
        html = render_to_string('qarz/qarz_detail.html', context, request=request)
        return JsonResponse({'html': html, 'detail_html': "detail_html", 'qarz_amount': float(qarz.amount)})
    return render(request, 'qarz/qarz.html',
                  context if 'context' in locals() else {'section': 'list', 'qarzlar': user_loans})


@login_required
def qarz_detail(request, qarz_id):
    """View loan details"""
    qarz = get_object_or_404(Qarz, id=qarz_id)
    if request.user != qarz.lender:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    context = {'qarz': qarz}
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        detail_html = render_to_string('qarz/qarz_detail.html', context, request=request)
        return JsonResponse({'html': detail_html, 'qarz_amount': float(qarz.amount)})
    return render(request, 'qarz/qarz.html', {'section': 'detail', 'qarz': qarz})


@login_required
def truck_details(request, truck_id):
    """View truck details"""
    truck = get_object_or_404(Truck, id=truck_id, user=request.user)
    context = {'section': 'truck_details', 'truck': truck}
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('qarz/qarz.html', context, request=request)
        return JsonResponse({'html': html})
    return render(request, 'qarz/qarz.html', context)