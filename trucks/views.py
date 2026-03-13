from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.db import transaction
from django.views.decorators.http import require_POST
from chiqim.models import Chiqim
from xarajatlar.models import Xarajat
from .models import Truck, TruckHujjat
from .forms import TruckForm, TruckHujjatForm
import os
from decimal import Decimal


def is_admin(user):
    return user.is_superuser


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "Successfully logged in!")
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password!")
    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    messages.success(request, "Successfully logged out!")
    return redirect('login')


@login_required
@user_passes_test(is_admin)
def user_list(request):
    users = User.objects.all().order_by('username')
    context = {'users': users}
    return render(request, 'user_list.html', context)


@login_required
@user_passes_test(is_admin)
def add_user(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        email = request.POST.get('email', '')
        if not username or not password:
            error_message = "Username and password are required!"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': {'username': "Username is required", 'password': "Password is required"}
                }, status=400)
            messages.error(request, error_message)
            return render(request, 'add_user_form.html')
        if User.objects.filter(username=username).exists():
            error_message = "This username is already taken!"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': {'username': "This username is already taken"}
                }, status=400)
            messages.error(request, error_message)
            return render(request, 'add_user_form.html')
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, password=password, email=email)
                user.save()
                success_message = f"User {username} successfully added!"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': success_message,
                        'redirect_url': reverse('user_list')
                    })
                messages.success(request, success_message)
                return redirect('user_list')
        except Exception as e:
            error_message = f"Error adding user: {str(e)}"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': {'__all__': str(e)}
                }, status=400)
            messages.error(request, error_message)
            return render(request, 'add_user_form.html')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('add_user_form.html', request=request)
        return JsonResponse({'success': True, 'html': html})
    return render(request, 'add_user_form.html')


@login_required
@user_passes_test(is_admin)
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email', '')
        password = request.POST.get('password', '')
        with transaction.atomic():
            if User.objects.filter(username=username).exclude(id=user_id).exists():
                messages.error(request, "This username is already taken!")
                return render(request, 'edit_user_form.html', {'user': user})
            user.username = username
            user.email = email
            if password:
                user.set_password(password)
            user.save()
            messages.success(request, f"User {username} successfully updated!")
            return redirect('user_list')
    return render(request, 'edit_user_form.html', {'user': user})


@login_required
@user_passes_test(is_admin)
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        if user.is_superuser:
            messages.error(request, "Superuser cannot be deleted!")
            return redirect('user_list')
        with transaction.atomic():
            username = user.username
            user.delete()
            messages.success(request, f"User {username} successfully deleted!")
            return redirect('user_list')
    return render(request, 'confirm_user_delete.html', {'user': user})


@login_required
def dashboard(request):
    query = request.GET.get('q', '')
    if request.user.is_superuser:
        trucks = Truck.objects.filter(sotilgan=False).select_related('user')
    else:
        trucks = Truck.objects.filter(user=request.user, sotilgan=False)

    if query:
        trucks = trucks.filter(
            Q(make__icontains=query) |
            Q(model__icontains=query) |
            Q(location__icontains=query) |
            Q(company__icontains=query) |
            Q(description__icontains=query) |
            Q(seriya__icontains=query) |
            Q(po_id__icontains=query)
        )

    # Calculate total expenses in a single query
    xarajatlar = Xarajat.objects.filter(truck__in=trucks).values('truck_id').annotate(total_xarajat=Sum('amount'))
    xarajat_dict = {x['truck_id']: x['total_xarajat'] for x in xarajatlar}

    paginator = Paginator(trucks, 10)
    page_number = request.GET.get('page')
    trucks_page = paginator.get_page(page_number)

    total_price = trucks.aggregate(total=Sum('price'))['total'] or 0
    total_xarajat = sum(xarajat_dict.values()) or 0

    context = {
        'trucks': trucks_page,
        'total_price': float(total_price) if total_price else 0,
        'total_xarajat': float(total_xarajat) if total_xarajat else 0,
    }
    return render(request, 'dashboard.html', context)


@login_required
def add_truck(request):
    if request.method == 'POST':
        form = TruckForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                truck = form.save(commit=False)
                if not request.user.is_superuser:
                    truck.user = request.user
                truck.save()
                success_message = f"{truck.po_id}: {truck.make} {truck.model} successfully added!"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'truck_id': truck.id,
                        'message': success_message,
                        'redirect': reverse('trucks_list')
                    })
                messages.success(request, success_message)
                return redirect('trucks_list')
        else:
            errors = form.errors.get_json_data()
            error_message = "Please correct the errors."
            if 'po_id' in errors:
                error_message = errors['po_id'][0]['message']
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': errors
                }, status=400)
            messages.error(request, error_message)
    else:
        form = TruckForm(user=request.user)

    return render(request, 'trucks/add_truck_form.html', {'form': form})


# ─────────────────────────────────────────────
# TRUCK: EDIT
# ─────────────────────────────────────────────

@login_required
def edit_truck(request, truck_id):
    truck = get_object_or_404(Truck, id=truck_id)

    # Ruxsat tekshirish
    if not request.user.is_superuser and truck.user != request.user:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)
        messages.error(request, "You do not have permission to edit this truck!")
        return redirect('trucks_list')

    if request.method == 'POST':
        form = TruckForm(request.POST, request.FILES, instance=truck, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                truck = form.save(commit=False)
                if not request.user.is_superuser:
                    truck.user = request.user
                truck.save()
                success_message = f"Truck {truck.po_id} successfully updated!"
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': success_message,
                        'truck_id': truck.id,
                        'po_id': truck.po_id
                    })
                messages.success(request, success_message)
                return redirect('trucks_list')
        else:
            errors = form.errors.get_json_data()
            error_message = "Please correct the errors."
            if 'po_id' in errors:
                error_message = errors['po_id'][0]['message']
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': errors
                }, status=400)
            messages.error(request, error_message)
    else:
        form = TruckForm(instance=truck, user=request.user)

    return render(request, 'trucks/edit_truck_form.html', {'form': form, 'truck': truck})


@require_POST
@login_required
def upload_hujjat(request):
    if not request.FILES:
        return JsonResponse({
            'success': False,
            'message': 'Please select at least one file!'
        }, status=400)

    truck_id = request.POST.get('truck_id')
    try:
        truck = Truck.objects.get(id=truck_id)
    except Truck.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Truck not found!'
        }, status=404)

    # Check permissions
    if truck.user != request.user and not request.user.is_superuser:
        raise PermissionDenied("You do not have permission to upload documents for this truck!")

    files = request.FILES.getlist('hujjat')
    hujjatlar = []

    with transaction.atomic():
        for file in files:
            try:
                # Validate file extension
                ext = file.name.split('.')[-1].lower()
                allowed_extensions = ['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']
                if ext not in allowed_extensions:
                    return JsonResponse({
                        'success': False,
                        'message': f"File '{file.name}' format is not supported! Only {', '.join(allowed_extensions)} are allowed!"
                    }, status=400)

                # Validate file size
                if file.size > 10 * 1024 * 1024:  # 10MB
                    return JsonResponse({
                        'success': False,
                        'message': f"File '{file.name}' size must be less than 10MB!"
                    }, status=400)

                # Create and save the document
                hujjat = TruckHujjat.objects.create(
                    truck=truck,
                    hujjat=file,
                    original_file_name=file.name
                )
                hujjatlar.append({
                    'id': hujjat.id,
                    'original_file_name': hujjat.original_file_name,
                    'hujjat_url': hujjat.hujjat.url
                })
            except Exception as e:
                transaction.set_rollback(True)
                return JsonResponse({
                    'success': False,
                    'message': f"Error uploading file '{file.name}': {str(e)}"
                }, status=500)

    all_hujjatlar = [{
        'id': h.id,
        'original_file_name': h.original_file_name,
        'hujjat_url': h.hujjat.url
    } for h in truck.hujjatlar.all()]

    return JsonResponse({
        'success': True,
        'message': "Documents successfully uploaded!",
        'hujjatlar': all_hujjatlar
    })

@login_required
def download_hujjat(request, hujjat_id):
    hujjat = get_object_or_404(TruckHujjat, id=hujjat_id)
    if hujjat.truck.user != request.user and not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': "You do not have permission to download this document!"}, status=403)

    file_path = hujjat.hujjat.path
    if os.path.exists(file_path):
        with open(file_path, 'rb') as file:
            response = HttpResponse(file.read(), content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{hujjat.original_file_name}"'
            return response
    else:
        return JsonResponse({'success': False, 'message': "File not found!"}, status=404)


# @login_required
# def edit_truck(request, truck_id):
#     truck = get_object_or_404(Truck, id=truck_id)
#     if not request.user.is_superuser and truck.user != request.user:
#         return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)
#
#     if request.method == 'POST':
#         form = TruckForm(request.POST, request.FILES, instance=truck, user=request.user)
#         if form.is_valid():
#             with transaction.atomic():
#                 truck = form.save(commit=False)
#                 if not request.user.is_superuser:
#                     truck.user = request.user
#                 truck.save()
#                 if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
#                     return JsonResponse({
#                         'success': True,
#                         'message': f"Truck {truck.po_id} successfully updated!",
#                         'truck_id': truck.id,
#                         'po_id': truck.po_id
#                     })
#                 messages.success(request, f"Truck {truck.po_id} successfully updated!")
#                 return redirect('dashboard')
#         else:
#             errors = form.errors.get_json_data()
#             error_message = "Please correct the errors."
#             if 'po_id' in errors:
#                 error_message = errors['po_id'][0]['message']
#             if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
#                 return JsonResponse({
#                     'success': False,
#                     'message': error_message,
#                     'errors': errors
#                 }, status=400)
#             messages.error(request, error_message)
#     else:
#         form = TruckForm(instance=truck, user=request.user)
#
#     if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
#         html = render_to_string('edit_truck_form.html', {'form': form, 'truck': truck}, request=request)
#         return JsonResponse({'success': True, 'html': html})
#
#     return render(request, 'edit_truck_form.html', {'form': form, 'truck': truck})


@login_required
def delete_truck(request, truck_id):
    if request.user.is_superuser:
        truck = get_object_or_404(Truck, id=truck_id)
    else:
        truck = get_object_or_404(Truck, id=truck_id, user=request.user)

    if request.method == 'POST':
        with transaction.atomic():
            # Chiqimlarni truck dan uzish (o'chirmaslik)
            Chiqim.objects.filter(truck=truck).update(truck=None)

            # Hujjatlarni fayl bilan birga o'chirish
            for hujjat in truck.hujjatlar.all():
                try:
                    if hujjat.hujjat and os.path.exists(hujjat.hujjat.path):
                        os.remove(hujjat.hujjat.path)
                except Exception:
                    pass
                hujjat.delete()

            truck_name = f"{truck.po_id}: {truck.make} {truck.model}"
            truck.delete()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f"{truck_name} successfully deleted!"
                })
            messages.success(request, f"{truck_name} successfully deleted!")
            return redirect('trucks_list')

    # GET - tasdiqlash sahifasi
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('confirm_delete_modal.html', {'truck': truck}, request=request)
        return JsonResponse({'html': html})
    return render(request, 'confirm_delete_modal.html', {'truck': truck})


@login_required
def delete_hujjat(request, hujjat_id):
    hujjat = get_object_or_404(TruckHujjat, id=hujjat_id)
    truck = hujjat.truck
    if truck.user != request.user and not request.user.is_superuser:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': "You do not have permission to delete this document!"})
        messages.error(request, "You do not have permission to delete this document!")
        return redirect('trucks_list')
    if request.method == 'POST':
        with transaction.atomic():
            if hujjat.hujjat and os.path.exists(hujjat.hujjat.path):
                os.remove(hujjat.hujjat.path)
            hujjat.delete()
            hujjatlar = [{
                'id': h.id,
                'original_file_name': h.original_file_name,
                'hujjat_url': h.hujjat.url
            } for h in truck.hujjatlar.all()]
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': "Document successfully deleted!",
                    'hujjatlar': hujjatlar
                })
            messages.success(request, "Document successfully deleted!")
            return redirect('trucks_list')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('delete_hujjat.html', {'hujjat': hujjat, 'truck': truck}, request=request)
        return JsonResponse({'html': html})
    return render(request, 'delete_hujjat.html', {'hujjat': hujjat, 'truck': truck})


@login_required
def trucks_list(request):
    query = request.GET.get('q', '').strip()

    if request.user.is_superuser:
        trucks = Truck.objects.all().select_related('user').order_by('-id')
    else:
        trucks = Truck.objects.filter(user=request.user).order_by('-id')

    if query:
        trucks = trucks.filter(
            Q(make__icontains=query) |
            Q(model__icontains=query) |
            Q(location__icontains=query) |
            Q(company__icontains=query) |
            Q(description__icontains=query) |
            Q(seriya__icontains=query) |
            Q(po_id__icontains=query)
        )

    # Barcha xarajatlarni bitta DB so'rovda hisoblash
    xarajatlar = (
        Xarajat.objects
        .filter(truck__in=trucks)
        .values('truck_id')
        .annotate(total_xarajat=Sum('amount'))
    )
    xarajat_dict = {
        x['truck_id']: x['total_xarajat'] or Decimal('0')
        for x in xarajatlar
    }

    # Umumiy summalar (paginatsiyadan OLDIN, butun queryset bo'yicha)
    total_price = trucks.aggregate(total=Sum('price'))['total'] or Decimal('0')
    total_xarajat_all = sum(xarajat_dict.values(), Decimal('0'))
    total_umumiy_all = total_price + total_xarajat_all

    paginator = Paginator(trucks, 10)
    page_number = request.GET.get('page')
    trucks_page = paginator.get_page(page_number)

    # Har bir truck uchun xarajat va umumiy narxni hisoblash
    trucks_data = []
    for truck in trucks_page:
        xarajat_sum = xarajat_dict.get(truck.id, Decimal('0'))
        umumiy_narx = (truck.price or Decimal('0')) + xarajat_sum
        trucks_data.append({
            'truck': truck,
            'xarajat_sum': float(xarajat_sum),
            'umumiy_narx': float(umumiy_narx),
        })

    context = {
        'trucks_data': trucks_data,
        'trucks': trucks_page,
        'total_price': float(total_price),
        'total_xarajat': float(total_xarajat_all),
        'total_umumiy': float(total_umumiy_all),
    }
    return render(request, 'trucks/trucks_list.html', context)


@require_POST
@login_required
def toggle_truck_status(request, truck_id):
    if request.user.is_superuser:
        truck = get_object_or_404(Truck, id=truck_id)
    else:
        truck = get_object_or_404(Truck, id=truck_id, user=request.user)
    truck.sotilgan = not truck.sotilgan
    truck.save(update_fields=['sotilgan'])
    return JsonResponse({
        'success': True,
        'sotilgan': truck.sotilgan,
        'label': 'Sold' if truck.sotilgan else 'Active',
    })


@login_required
def truck_detail(request, truck_id):
    if request.user.is_superuser:
        truck = get_object_or_404(Truck, id=truck_id)
    else:
        truck = get_object_or_404(Truck, id=truck_id, user=request.user)

    xarajatlar = Xarajat.objects.filter(truck=truck)
    total_xarajat = xarajatlar.aggregate(total=Sum('amount'))['total'] or 0
    total_cost = float(truck.price + total_xarajat)

    hujjatlar = [{
        'id': h.id,
        'original_file_name': h.original_file_name,
        'hujjat_url': reverse('download_hujjat', args=[h.id])
    } for h in truck.hujjatlar.all()]

    context = {
        'truck': truck,
        'xarajatlar': xarajatlar,
        'xarajat_sum': total_xarajat,
        'umumiy_narx': total_cost,
        'hujjatlar': hujjatlar,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'hujjatlar': hujjatlar})

    return render(request, 'trucks/truck_detail_page.html', context)