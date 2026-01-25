# tasks.py
from __future__ import absolute_import, unicode_literals
import smtplib
import logging
from datetime import date
from time import sleep

from celery import shared_task
from django.conf import settings
from django.core.mail import get_connection, send_mail
from django.db import transaction
from django.utils import timezone

from .models import Bildirishnoma, EmailHistory

logger = logging.getLogger(__name__)


# tasks.py  (faqat kerakli qismlar)

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def check_payment_reminders(self):
    """
    Har kuni ishlaydigan Celery task:
    1. Tolanmagan barcha bildirishnomalarni tekshiradi
    2. Qarz tugamaguncha har 1 kunda 1 marta e-pochta yuboradi
    3. 5,4,3,2,1 kun qolgan va overdue holatlarida qayta-qayta ogohlantiradi
    """
    current_date = date.today()
    notifications = Bildirishnoma.objects.filter(
        chiqim__qoldiq_summa__gt=0,   # to‘lanmagan
        tolov_sana__isnull=False,
        chiqim__isnull=False,
        chiqim__xaridor__isnull=False,
        chiqim__xaridor__user__isnull=False,
    ).select_related('chiqim__xaridor__user', 'chiqim__truck')

    logger.info(f"[check_payment_reminders] {len(notifications)} ta bildirishnoma topildi.")

    for notification in notifications:
        try:
            _send_single_reminder(notification, current_date)
        except Exception as exc:
            logger.exception(f"[check_payment_reminders] Xatolik ID {notification.id}: {exc}")


def _send_single_reminder(notification, current_date):
    """
    Bitta bildirishnomaga tegishli email yuborish logikasi.
    Overdue yoki 1-5 kun qolganda har kuni yuboradi.
    """
    days_left = (notification.tolov_sana - current_date).days
    paid_for_month = notification.chiqim.already_paid_for_month(notification.tolov_sana)

    # Agar bu oyga to‘liq to‘langan bo‘lsa — hech narsa qilma
    if paid_for_month:
        logger.info(f"[ID {notification.id}] Bu oyga to‘langan, skipped.")
        return

    # Agar 5,4,3,2,1 kun qolgan yoki overdue bo‘lsa – yuborish zarur
    should_send = (
        days_left in (5, 4, 3, 2, 1) or
        days_left <= 0
    )

    if not should_send:
        logger.info(f"[ID {notification.id}] Hali {days_left} kun qoldi, skipped.")
        return

    xaridor = notification.chiqim.xaridor
    email = (xaridor.email or "").strip()
    if not email:
        logger.warning(f"[ID {notification.id}] Email manzil yo‘q, skipped.")
        return

    truck = notification.chiqim.truck
    truck_info = f"{truck.make} {truck.model}" if truck else "Unknown Vehicle"
    subject = f"Payment Reminder for {truck_info}"
    full_name = xaridor.ism_familiya or "Valued Customer"

    # Overdue bo‘lsa matnni boshqacha qilamiz
    if days_left <= 0:
        overdue_days = abs(days_left)
        message = (
            f"Dear {full_name},\n\n"
            f"This is an URGENT reminder from NCL TRUCK SALES INC.\n"
            f"Your monthly payment for {truck_info} was due on {notification.tolov_sana}.\n"
            f"You are now {overdue_days} day(s) overdue.\n"
            f"Please make the payment immediately to avoid additional fees and legal action.\n\n"
            f"Thank you for your immediate attention.\n\n"
            f"Sincerely,\n"
            f"NCL TRUCK SALES INC\n"
            f"Billing Department"
        )
    else:
        message = (
            f"Dear {full_name},\n\n"
            f"This is a reminder from NCL TRUCK SALES INC that your monthly payment for {truck_info} is due on {notification.tolov_sana}.\n"
            f"You have {days_left} day(s) left to pay.\n\n"
            f"Please make sure to submit your payment on time to avoid a late fee.\n"
            f"If you have already made the payment, please disregard this message.\n\n"
            f"Thank you for your prompt attention.\n\n"
            f"Sincerely,\n"
            f"NCL TRUCK SALES INC\n"
            f"Billing Department"
        )

    conn = get_connection(
        backend=settings.EMAIL_BACKEND,
        host=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        username=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS,
        use_ssl=getattr(settings, "EMAIL_USE_SSL", False),
        timeout=30,
    )

    try:
        conn.open()
        result = send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
            connection=conn,
        )
        conn.close()

        if result == 1:
            with transaction.atomic():
                EmailHistory.objects.create(
                    bildirishnoma=notification,
                    subject=subject,
                    message=message,
                    recipient=email,
                    status='success',
                )
                # email_sent=False qoldiramiz – har kuni yuborishimiz kerak
            logger.info(f"[ID {notification.id}] Email muvaffaqiyatli yuborildi → {email}")
        else:
            raise Exception("send_mail 0 qaytardi.")

    except (smtplib.SMTPException, OSError) as exc:
        logger.warning(f"[ID {notification.id}] SMTP xatolik: {exc}. Qayta uriniladi.")
        raise exc
    except Exception as exc:
        logger.error(f"[ID {notification.id}] Umumiy xatolik: {exc}")
        EmailHistory.objects.create(
            bildirishnoma=notification,
            subject=subject,
            message=message,
            recipient=email,
            status='failed',
            error_message=str(exc),
        )
