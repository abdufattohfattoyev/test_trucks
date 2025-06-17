from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from .models import Xaridor, XaridorHujjat
from .forms import XaridorForm, XaridorHujjatForm
from chiqim.models import Chiqim
from trucks.models import Truck
import os
import logging
from datetime import datetime
from django.db import models

logger = logging.getLogger(__name__)

@login_required
def xaridorlar_list(request):
    query = request.GET.get('q', '')
    sana = request.GET.get('sana', '')

    if request.user.is_superuser:
        xaridorlar = Xaridor.objects.all().order_by('-sana')
    else:
        xaridorlar = Xaridor.objects.filter(user=request.user).order_by('-id')

    if query:
        xaridorlar = xaridorlar.filter(
            models.Q(ism_familiya__icontains=query) |
            models.Q(telefon_raqam__icontains=query) |
            models.Q(email__icontains=query)
        )

    if sana:
        try:
            sana_dt = datetime.strptime(sana, '%Y-%m-%d').date()
            xaridorlar = xaridorlar.filter(sana=sana_dt)
        except ValueError:
            messages.error(request, "Noto'g'ri sana formati. YYYY-MM-DD formatida kiriting!")

    paginator = Paginator(xaridorlar, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'query': query,
        'sana': sana,
        'is_superuser': request.user.is_superuser,
    }
    return render(request, 'xaridorlar/xaridorlar_list.html', context)

@login_required
def xaridor_add(request):
    xaridor_form = XaridorForm(request.POST or None)
    hujjat_form = XaridorHujjatForm()

    if request.method == 'POST':
        logger.debug(f"POST data: {request.POST}, FILES: {request.FILES}")
        if xaridor_form.is_valid():
            xaridor = xaridor_form.save(commit=False)
            xaridor.user = request.user
            xaridor.save()

            files = request.FILES.getlist('hujjat')
            for file in files:
                hujjat = XaridorHujjat(xaridor=xaridor, hujjat=file)
                hujjat.original_filename = file.name
                hujjat.save()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'xaridor_id': xaridor.id,
                    'message': "Xaridor muvaffaqiyatli qo'shildi!",
                    'redirect_url': reverse('xaridorlar_list')
                })
            messages.success(request, "Xaridor muvaffaqiyatli qo'shildi!")
            return redirect('xaridorlar_list')
        else:
            logger.error(f"Form errors: {xaridor_form.errors}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': xaridor_form.errors.as_json(),
                    'message': "Forma to'ldirishda xatolik yuz berdi!"
                })
            messages.error(request, "Iltimos, formani to'g'ri to'ldiring!")

    context = {
        'xaridor_form': xaridor_form,
        'hujjat_form': hujjat_form
    }
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xaridorlar/add_xaridor.html', context, request=request)
        return JsonResponse({'html': html})

    return render(request, 'xaridorlar/add_xaridor.html', context)

@login_required
def upload_hujjat(request):
    if request.method == 'POST':
        xaridor_id = request.POST.get('xaridor_id')
        xaridor = get_object_or_404(Xaridor, id=xaridor_id)
        if xaridor.user != request.user and not request.user.is_superuser:
            logger.warning(f"User {request.user} attempted to upload documents for Xaridor {xaridor.id} without permission.")
            return JsonResponse({'success': False, 'message': "Bu xaridorga hujjat qo'shishga ruxsatingiz yo'q!"})

        files = request.FILES.getlist('hujjat')
        if not files:
            logger.warning(f"No files found in request.FILES: {request.FILES}")
            return JsonResponse({'success': False, 'message': "Fayl tanlanmadi!"})

        uploaded_hujjatlar = []
        try:
            for file in files:
                hujjat = XaridorHujjat(xaridor=xaridor, hujjat=file)
                hujjat.original_filename = file.name
                hujjat.save()
                uploaded_hujjatlar.append({
                    'id': hujjat.id,
                    'original_filename': hujjat.original_filename,
                    'hujjat_url': hujjat.hujjat.url
                })
        except Exception as e:
            logger.error(f"Error uploading documents for Xaridor {xaridor.id}: {str(e)}")
            return JsonResponse({'success': False, 'message': f"Hujjat yuklashda xato: {str(e)}"})

        hujjatlar = [{
            'id': h.id,
            'original_filename': h.original_filename,
            'hujjat_url': h.hujjat.url
        } for h in xaridor.hujjatlar.all()]

        return JsonResponse({
            'success': True,
            'message': f"{len(uploaded_hujjatlar)} ta hujjat muvaffaqiyatli yuklandi!",
            'hujjatlar': hujjatlar
        })

    return JsonResponse({'success': False, 'message': "Faqat POST so'rovlarni qabul qilamiz!"})

@login_required
def xaridor_edit(request, id):
    xaridor = get_object_or_404(Xaridor, id=id)
    if xaridor.user != request.user and not request.user.is_superuser:
        logger.warning(f"User {request.user} attempted to edit Xaridor {xaridor.id} without permission.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': "Bu xaridorni tahrirlashga ruxsatingiz yo'q!"})
        messages.error(request, "Bu xaridorni tahrirlashga ruxsatingiz yo'q!")
        return redirect('xaridorlar_list')

    if request.method == 'POST':
        xaridor_form = XaridorForm(request.POST, instance=xaridor)
        if xaridor_form.is_valid():
            xaridor_form.save()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': "Xaridor muvaffaqiyatli tahrirlandi!",
                    'redirect_url': reverse('xaridorlar_list')
                })
            messages.success(request, "Xaridor muvaffaqiyatli tahrirlandi!")
            return redirect('xaridorlar_list')
        else:
            logger.error(f"Edit form errors: {xaridor_form.errors}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': xaridor_form.errors.as_json(),
                    'message': "Forma to'ldirishda xatolik yuz berdi!"
                })
            messages.error(request, "Xatolik yuz berdi! Iltimos, formani to'g'ri to'ldiring!")

    xaridor_form = XaridorForm(instance=xaridor)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xaridorlar/edit_xaridor.html', {
            'xaridor_form': xaridor_form,
            'xaridor': xaridor
        }, request=request)
        return JsonResponse({'html': html})

    return render(request, 'xaridorlar/edit_xaridor.html', {
        'xaridor_form': xaridor_form,
        'xaridor': xaridor
    })

@login_required
def xaridor_delete(request, id):
    xaridor = get_object_or_404(Xaridor, id=id)
    if xaridor.user != request.user and not request.user.is_superuser:
        logger.warning(f"User {request.user} attempted to delete Xaridor {xaridor.id} without permission.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': "Bu xaridorni o'chirishga ruxsatingiz yo'q!"})
        messages.error(request, "Bu xaridorni o'chirishga ruxsatingiz yo'q!")
        return redirect('xaridorlar_list')

    if request.method == 'POST':
        chiqimlar = Chiqim.objects.filter(xaridor=xaridor)
        for chiqim in chiqimlar:
            truck = chiqim.truck
            if truck:
                truck.sotilgan = False
                truck.save()

        for hujjat in xaridor.hujjatlar.all():
            try:
                if hujjat.hujjat and os.path.exists(hujjat.hujjat.path):
                    os.remove(hujjat.hujjat.path)
            except Exception as e:
                logger.error(f"Error deleting file {hujjat.hujjat.path}: {str(e)}")
        xaridor.delete()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': "Xaridor muvaffaqiyatli o'chirildi!"
            })
        messages.success(request, "Xaridor muvaffaqiyatli o'chirildi!")
        return redirect('xaridorlar_list')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xaridorlar/delete_xaridor.html', {'xaridor': xaridor}, request=request)
        return JsonResponse({'html': html})

    return render(request, 'xaridorlar/delete_xaridor.html', {'xaridor': xaridor})

@login_required
def view_passport(request, id):
    xaridor = get_object_or_404(Xaridor, id=id)
    if xaridor.user != request.user and not request.user.is_superuser:
        logger.warning(f"User {request.user} attempted to view documents for Xaridor {xaridor.id} without permission.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': "Bu xaridorning hujjatini ko'rishga ruxsatingiz yo'q!"})
        messages.error(request, "Bu xaridorning hujjatini ko'rishga ruxsatingiz yo'q!")
        return redirect('xaridorlar_list')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xaridorlar/view_passport.html', {'xaridor': xaridor}, request=request)
        return JsonResponse({'html': html})

    return render(request, 'xaridorlar/view_passport.html', {'xaridor': xaridor})

@login_required
def delete_hujjat(request, hujjat_id):
    logger.debug(f"delete_hujjat started: hujjat_id={hujjat_id}, user={request.user}")
    hujjat = get_object_or_404(XaridorHujjat, id=hujjat_id)
    xaridor = hujjat.xaridor

    # Permission check
    if xaridor.user != request.user and not request.user.is_superuser:
        logger.warning(f"User {request.user} attempted to delete document {hujjat_id} without permission.")
        return JsonResponse({
            'success': False,
            'message': "Bu hujjatni o'chirishga ruxsatingiz yo'q!"
        }, status=403)

    if request.method == 'POST':
        try:
            # Get file path
            file_path = hujjat.hujjat.path if hujjat.hujjat else None

            # Delete from database
            hujjat.delete()

            # Delete physical file
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"File successfully deleted: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {str(e)}")
                    # Continue even if file deletion fails, as DB record is already deleted

            # Prepare remaining documents
            remaining_hujjats = xaridor.hujjatlar.all()
            hujjatlar_list = [{
                'id': h.id,
                'original_filename': h.original_filename,
                'hujjat_url': h.hujjat.url,
                'uploaded_at': h.uploaded_at.strftime("%d.%m.%Y %H:%M")
            } for h in remaining_hujjats]

            logger.info(f"Document successfully deleted: ID {hujjat_id}")

            return JsonResponse({
                'success': True,
                'message': "Hujjat muvaffaqiyatli o'chirildi!",
                'hujjatlar': hujjatlar_list,
                'has_hujjats': remaining_hujjats.exists(),
                'xaridor_id': xaridor.id
            })

        except Exception as e:
            logger.error(f"Error deleting document {hujjat_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': f"Hujjatni o'chirishda xatolik yuz berdi: {str(e)}"
            }, status=500)

    return JsonResponse({
        'success': False,
        'message': "Noto'g'ri so'rov turi! Faqat POST so'rovlari qabul qilinadi."
    }, status=405)