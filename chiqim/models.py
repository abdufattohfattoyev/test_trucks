from decimal import Decimal
import calendar
import logging
import uuid
from django.db import DatabaseError
from django.db import models, transaction
from django.utils import timezone
from trucks.models import Truck
from django.utils.text import slugify
import os
from .telegram_utils import send_to_telegram, send_file_to_telegram
from typing import Optional

logger = logging.getLogger(__name__)

def generate_unique_chiqim_filename(instance, filename):
    """Generate a unique filename based on truck_id for document storage."""
    ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4()}{ext}"
    truck_id = instance.truck.id if instance.truck else 'unknown'
    return os.path.join(f'chiqim_documents/{truck_id}/', slugify(unique_name))

class Chiqim(models.Model):
    truck = models.ForeignKey(
        Truck,
        on_delete=models.CASCADE,
        related_name='chiqim',
        verbose_name="Vehicle"
    )
    xaridor = models.ForeignKey(
        'xaridorlar.Xaridor',
        on_delete=models.CASCADE,
        related_name='chiqim',
        verbose_name="Buyer"
    )
    narx = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Total Price"
    )
    boshlangich_summa = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Initial Payment (Planned)"
    )
    qoldiq_summa = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Remaining Amount"
    )
    hujjatlar = models.FileField(
        upload_to=generate_unique_chiqim_filename,
        blank=True,
        null=True,
        verbose_name="Documents"
    )
    original_file_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Original File Name"
    )
    bo_lib_tolov_muddat = models.PositiveIntegerField(
        default=0,
        verbose_name="Installment Period (Months)"
    )
    oyiga_tolov = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Monthly Payment"
    )
    tolov_sana = models.DateField(verbose_name="First Payment Date")
    izoh = models.TextField(blank=True, verbose_name="Notes")
    sana = models.DateField(auto_now_add=True, verbose_name="Sale Date")

    def get_user_full_name(self) -> str:
        """Return the full name of the associated user."""
        full_name = f"{self.xaridor.user.first_name} {self.xaridor.user.last_name}".strip()
        return full_name or self.xaridor.user.username

    def get_total_boshlangich_paid(self):
        if not self.pk:
            return Decimal('0')
        return sum(tolov.summa for tolov in self.boshlangich_tolovlar.all()) or Decimal('0')

    def get_total_monthly_paid(self):
        if not self.pk:
            return Decimal('0')
        return sum(tolov.summa for tolov in self.tolovlar.all()) or Decimal('0')

    def get_boshlangich_qoldiq(self):
        """Calculate the remaining initial payment."""
        return max(Decimal('0'), self.boshlangich_summa - self.get_total_boshlangich_paid())

    def calculate_monthly_payment(self):
        remaining_amount = self.narx - self.boshlangich_summa
        if self.bo_lib_tolov_muddat > 0 and remaining_amount > 0:
            self.oyiga_tolov = remaining_amount / Decimal(str(self.bo_lib_tolov_muddat))
        else:
            self.oyiga_tolov = Decimal('0')

    def update_totals(self, save=True):
        if not self.pk:
            logger.warning(f"Sale object (no ID) not saved, as PK is missing")
            return

        try:
            total_boshlangich_paid = self.get_total_boshlangich_paid()
            total_monthly_paid = self.get_total_monthly_paid()
            total_paid = total_boshlangich_paid + total_monthly_paid
            self.qoldiq_summa = max(Decimal('0'), self.narx - total_paid)
            self.calculate_monthly_payment()

            if self.qoldiq_summa <= 0:
                self.bo_lib_tolov_muddat = 0
                self.oyiga_tolov = Decimal('0')
                self.bildirishnomalar.all().delete()
                logger.debug(f"Sale ID {self.id} remaining amount is 0, notifications deleted")
            else:
                if self.bo_lib_tolov_muddat <= 0 and total_monthly_paid > 0:
                    remaining_amount = self.qoldiq_summa
                    self.oyiga_tolov = self.oyiga_tolov if self.oyiga_tolov else remaining_amount
                    self.bo_lib_tolov_muddat = int(remaining_amount // self.oyiga_tolov) if self.oyiga_tolov > 0 else 0
                    logger.debug(f"Sale ID {self.id} period updated: {self.bo_lib_tolov_muddat}")

            if save:
                if Chiqim.objects.filter(id=self.id).exists():
                    self.save(update_fields=['qoldiq_summa', 'oyiga_tolov', 'bo_lib_tolov_muddat'], skip_telegram=True)
                    logger.debug(f"Sale ID {self.id} successfully saved")
                else:
                    logger.warning(f"Sale ID {self.id} not found in database")
        except DatabaseError as e:
            logger.error(f"Error saving Sale ID {self.id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error for Sale ID {self.id}: {str(e)}")
            raise

    @property
    def tolangan_summa(self):
        return self.get_total_boshlangich_paid() + self.get_total_monthly_paid()

    def get_next_unpaid_month(self):
        current_date = timezone.now().date()
        return self.bildirishnomalar.filter(
            status__in=['pending', 'warning', 'urgent', 'overdue'],
            tolov_sana__gte=current_date
        ).order_by('tolov_sana').first()

    def save(self, *args, skip_telegram=False, **kwargs):
        is_new = not self.pk
        old_instance = None
        old_truck = None
        significant_change = is_new
        telegram_message = None
        telegram_file = None

        with transaction.atomic():
            if not self.tolov_sana:
                self.tolov_sana = timezone.now().date()
                logger.warning(
                    f"Sale ID {self.id or 'new'} has no tolov_sana, setting to current date: {self.tolov_sana}")

            if not is_new:
                try:
                    old_instance = Chiqim.objects.get(pk=self.pk)
                    old_truck = old_instance.truck if old_instance.truck != self.truck else None
                    significant_change = (
                            old_instance.narx != self.narx or
                            old_instance.boshlangich_summa != self.boshlangich_summa or
                            old_instance.bo_lib_tolov_muddat != self.bo_lib_tolov_muddat or
                            old_instance.tolov_sana != self.tolov_sana or
                            old_instance.izoh != self.izoh or
                            (old_instance.hujjatlar.name != self.hujjatlar.name if self.hujjatlar else False)
                    )
                    if significant_change:
                        self.calculate_monthly_payment()
                except Chiqim.DoesNotExist:
                    pass

            if is_new:
                self.qoldiq_summa = self.narx
                self.calculate_monthly_payment()
                if self.truck:
                    self.truck.sotilgan = True
                    self.truck.save()

            # Ensure oyiga_tolov is never None
            if self.oyiga_tolov is None:
                self.calculate_monthly_payment()
                if self.oyiga_tolov is None:  # Fallback in case calculate_monthly_payment doesn't set it
                    self.oyiga_tolov = Decimal('0')
                    logger.warning(f"Sale ID {self.id or 'new'} had None oyiga_tolov, set to 0")

            if self.hujjatlar and not self.original_file_name:
                self.original_file_name = os.path.basename(self.hujjatlar.name)

            super().save(*args, **kwargs)
            self.update_totals(save=False)

            if old_truck and old_truck != self.truck:
                old_truck.sotilgan = False
                old_truck.save()
                self.truck.sotilgan = True
                self.truck.save()

            self.xaridor.update_financials()

            # Prepare Telegram message outside transaction
            if not skip_telegram and significant_change:
                action = "Created" if is_new else "Updated"
                action_emoji = "📄" if is_new else "🔄"
                izoh = self.izoh[:500] + '...' if self.izoh and len(self.izoh) > 500 else self.izoh or 'None'
                telegram_message = (
                    f"<b>{action_emoji} Sale {action}</b>\n"
                    f"📋 <u>Sale Details:</u>\n"
                    f"  • Buyer: {self.xaridor.ism_familiya}\n"
                    f"  • Vehicle: <code>{self.truck.po_id}</code> ({self.truck.make} {self.truck.model})\n"
                    f"  • Total Price: ${self.narx:,.2f}\n"
                    f"  • Initial Payment: ${self.boshlangich_summa:,.2f}\n"
                    f"  • Remaining Amount: ${self.qoldiq_summa:,.2f}\n"
                    f"  • Monthly Payment: ${self.oyiga_tolov or 0:,.2f}\n"
                    f"  • Installment Period: {self.bo_lib_tolov_muddat} months\n"
                    f"  • First Payment Date: {self.tolov_sana}\n"
                    f"  • Sale Date: {self.sana}\n"
                    f"  • Notes: {izoh}\n"
                    f"  • Document: <code>{self.original_file_name or 'None'}</code>\n"
                    f"\n👤 <u>Admin:</u>\n"
                    f"  • Username: <code>{self.xaridor.user.username}</code>\n"
                    f"  • Name: {self.get_user_full_name()}"
                )
                if self.hujjatlar:
                    telegram_file = {
                        'file_path': self.hujjatlar.path,
                        'original_filename': self.original_file_name or os.path.basename(self.hujjatlar.name),
                        'caption': (
                            f"<b>📎 Sale Document</b>\n"
                            f"Buyer: {self.xaridor.ism_familiya}\n"
                            f"Vehicle: <code>{self.truck.po_id}</code>\n"
                            f"File: <code>{self.original_file_name}</code>"  # Tuzatildi
                        )
                    }

        # Send Telegram message outside transaction
        if telegram_message:
            try:
                send_to_telegram(telegram_message)
                if telegram_file:
                    send_file_to_telegram(
                        telegram_file['file_path'],
                        telegram_file['original_filename'],
                        telegram_file['caption']
                    )
            except Exception as e:
                logger.error(f"Error sending Telegram message for Chiqim ID {self.id}: {str(e)}")

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            message = (
                f"<b>🗑️ Sale Deleted</b>\n"
                f"📋 <u>Sale Details:</u>\n"
                f"  • Buyer: {self.xaridor.ism_familiya}\n"
                f"  • Vehicle: <code>{self.truck.po_id}</code> ({self.truck.make} {self.truck.model})\n"
                f"  • Total Price: ${self.narx:,.2f}\n"
                f"  • Initial Payment: ${self.boshlangich_summa:,.2f}\n"
                f"  • Remaining Amount: ${self.qoldiq_summa:,.2f}\n"
                f"\n👤 <u>Admin:</u>\n"
                f"  • Username: <code>{self.xaridor.user.username}</code>\n"
                f"  • Name: {self.get_user_full_name()}"
            )
            self.bildirishnomalar.all().delete()
            self.tolovlar.all().delete()
            self.boshlangich_tolovlar.all().delete()
            if self.truck:
                self.truck.sotilgan = False
                self.truck.save()
            super().delete(*args, **kwargs)
            self.xaridor.update_financials()
            send_to_telegram(message)

    def __str__(self):
        return f"{self.truck.make} {self.truck.model} - {self.xaridor.ism_familiya}"

    class Meta:
        verbose_name = "Sale"
        verbose_name_plural = "Sales"
        indexes = [models.Index(fields=['sana']), models.Index(fields=['tolov_sana'])]

class BoshlangichTolov(models.Model):
    PAYMENT_TYPES = (
        ('zelle', 'Zelle'),
        ('wire_transfer', "Wire Transfer"),
        ('cash', 'Cash'),
        ('button', 'Button'),
    )
    chiqim = models.ForeignKey(
        Chiqim,
        on_delete=models.CASCADE,
        related_name='boshlangich_tolovlar',
        verbose_name="Sale"
    )
    xaridor = models.ForeignKey(
        'xaridorlar.Xaridor',
        on_delete=models.CASCADE,
        verbose_name="Buyer"
    )
    tolov_turi = models.CharField(
        max_length=20,
        choices=PAYMENT_TYPES,
        verbose_name="Payment Type"
    )
    summa = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Payment Amount"
    )
    firma_nomi = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Company Name"
    )
    bank = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Bank Used for Payment"
    )
    izoh = models.TextField(
        blank=True,
        verbose_name="Notes"
    )
    sana = models.DateField(
        verbose_name="Payment Date"
    )
    is_partial = models.BooleanField(
        default=False,
        verbose_name="Partial Payment"
    )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            is_new = not self.pk
            super().save(*args, **kwargs)
            self.chiqim.update_totals()
            self.xaridor.update_financials()

            action = "Created" if is_new else "Updated"
            action_emoji = "💰" if is_new else "🔄"
            izoh = self.izoh[:500] + '...' if self.izoh and len(self.izoh) > 500 else self.izoh or 'None'
            message = (
                f"<b>{action_emoji} Initial Payment {action}</b>\n"
                f"💸 <u>Payment Details:</u>\n"
                f"  • Buyer: {self.xaridor.ism_familiya}\n"
                f"  • Amount: ${self.summa:,.2f}\n"
                f"  • Payment Type: {self.get_tolov_turi_display()}\n"
                f"  • Company Name: {self.firma_nomi or 'None'}\n"
                f"  • Bank: {self.bank or 'None'}\n"
                f"  • Date: {self.sana}\n"
                f"  • Partial: {'Yes' if self.is_partial else 'No'}\n"
                f"  • Notes: {izoh}\n"
                f"\n📋 <u>Sale:</u>\n"
                f"  • Vehicle: <code>{self.chiqim.truck.po_id}</code> ({self.chiqim.truck.make} {self.chiqim.truck.model})\n"
                f"  • Remaining Amount: ${self.chiqim.qoldiq_summa:,.2f}\n"
                f"\n👤 <u>Admin:</u>\n"
                f"  • Username: <code>{self.xaridor.user.username}</code>\n"
                f"  • Name: {self.xaridor.get_user_full_name()}"
            )
            send_to_telegram(message)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            message = (
                f"<b>🗑️ Initial Payment Deleted</b>\n"
                f"💸 <u>Payment Details:</u>\n"
                f"  • Buyer: {self.xaridor.ism_familiya}\n"
                f"  • Amount: ${self.summa:,.2f}\n"
                f"  • Payment Type: {self.get_tolov_turi_display()}\n"
                f"  • Date: {self.sana}\n"
                f"\n📋 <u>Sale:</u>\n"
                f"  • Vehicle: <code>{self.chiqim.truck.po_id}</code> ({self.chiqim.truck.make} {self.chiqim.truck.model})\n"
                f"\n👤 <u>Admin:</u>\n"
                f"  • Username: <code>{self.xaridor.user.username}</code>\n"
                f"  • Name: {self.xaridor.get_user_full_name()}"
            )
            chiqim = self.chiqim
            super().delete(*args, **kwargs)
            chiqim.update_totals()
            self.xaridor.update_financials()
            send_to_telegram(message)

    def __str__(self):
        return f"{self.xaridor.ism_familiya} - Initial {self.get_tolov_turi_display()} (${self.summa})"

    class Meta:
        verbose_name = "Initial Payment"
        verbose_name_plural = "Initial Payments"
        indexes = [
            models.Index(fields=['sana']),
        ]

class TolovTuri(models.Model):
    PAYMENT_TYPES = (
        ('zelle', 'Zelle'),
        ('wire_transfer', "Wire Transfer"),
        ('cash', 'Cash'),
        ('button', 'Button'),
    )
    chiqim = models.ForeignKey(
        Chiqim,
        on_delete=models.CASCADE,
        related_name='tolovlar',
        verbose_name="Sale"
    )
    xaridor = models.ForeignKey(
        'xaridorlar.Xaridor',
        on_delete=models.CASCADE,
        verbose_name="Buyer"
    )
    tolov_turi = models.CharField(
        max_length=20,
        choices=PAYMENT_TYPES,
        verbose_name="Payment Type"
    )
    summa = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Payment Amount"
    )
    firma_nomi = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Company Name"
    )
    bank = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Bank Used for Payment"
    )
    izoh = models.TextField(
        blank=True,
        verbose_name="Notes"
    )
    sana = models.DateField(
        verbose_name="Payment Date"
    )
    is_partial = models.BooleanField(
        default=False,
        verbose_name="Partial Payment"
    )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            is_new = not self.pk
            super().save(*args, **kwargs)
            self.chiqim.update_totals()
            self.xaridor.update_financials()

            action = "Created" if is_new else "Updated"
            action_emoji = "💳" if is_new else "🔄"
            izoh = self.izoh[:500] + '...' if self.izoh and len(self.izoh) > 500 else self.izoh or 'None'
            message = (
                f"<b>{action_emoji} Monthly Payment {action}</b>\n"
                f"💸 <u>Payment Details:</u>\n"
                f"  • Buyer: {self.xaridor.ism_familiya}\n"
                f"  • Amount: ${self.summa:,.2f}\n"
                f"  • Payment Type: {self.get_tolov_turi_display()}\n"
                f"  • Company Name: {self.firma_nomi or 'None'}\n"
                f"  • Bank: {self.bank or 'None'}\n"
                f"  • Date: {self.sana}\n"
                f"  • Partial: {'Yes' if self.is_partial else 'No'}\n"
                f"  • Notes: {izoh}\n"
                f"\n📋 <u>Sale:</u>\n"
                f"  • Vehicle: <code>{self.chiqim.truck.po_id}</code> ({self.chiqim.truck.make} {self.chiqim.truck.model})\n"
                f"  • Remaining Amount: ${self.chiqim.qoldiq_summa:,.2f}\n"
                f"\n👤 <u>Admin:</u>\n"
                f"  • Username: <code>{self.xaridor.user.username}</code>\n"
                f"  • Name: {self.xaridor.get_user_full_name()}"
            )
            send_to_telegram(message)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            message = (
                f"<b>🗑️ Monthly Payment Deleted</b>\n"
                f"💸 <u>Payment Details:</u>\n"
                f"  • Buyer: {self.xaridor.ism_familiya}\n"
                f"  • Amount: ${self.summa:,.2f}\n"
                f"  • Payment Type: {self.get_tolov_turi_display()}\n"
                f"  • Date: {self.sana}\n"
                f"\n📋 <u>Sale:</u>\n"
                f"  • Vehicle: <code>{self.chiqim.truck.po_id}</code> ({self.chiqim.truck.make} {self.chiqim.truck.model})\n"
                f"\n👤 <u>Admin:</u>\n"
                f"  • Username: <code>{self.xaridor.user.username}</code>\n"
                f"  • Name: {self.xaridor.get_user_full_name()}"
            )
            chiqim = self.chiqim
            super().delete(*args, **kwargs)
            chiqim.update_totals()
            self.xaridor.update_financials()
            send_to_telegram(message)

    def __str__(self):
        return f"{self.xaridor.ism_familiya} - {self.get_tolov_turi_display()} (${self.summa})"

    class Meta:
        verbose_name = "Monthly Payment"
        verbose_name_plural = "Monthly Payments"
        indexes = [
            models.Index(fields=['sana']),
        ]

class BildirishnomaManager(models.Manager):
    def active(self, user=None):
        current_date = timezone.now().date()
        queryset = self.filter(
            chiqim__qoldiq_summa__gt=0,
            status__in=['pending', 'warning', 'urgent', 'overdue']
        )
        if user and not user.is_superuser:
            queryset = queryset.filter(
                chiqim__truck__user=user,
                chiqim__xaridor__user=user
            )
        return queryset

    def next_unpaid_for_chiqim(self, chiqim_id, user=None):
        current_date = timezone.now().date()
        queryset = self.filter(
            chiqim_id=chiqim_id,
            status__in=['pending', 'warning', 'urgent', 'overdue']
        )
        if user and not user.is_superuser:
            queryset = queryset.filter(
                chiqim__truck__user=user,
                chiqim__xaridor__user=user
            )
        return queryset.order_by('tolov_sana').first()

class Bildirishnoma(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('urgent', 'Urgent'),
        ('warning', 'Warning'),
    ]

    chiqim = models.ForeignKey(
        Chiqim,
        on_delete=models.CASCADE,
        related_name='bildirishnomalar',
        verbose_name="Sale"
    )
    tolov_sana = models.DateField(verbose_name="Payment Date")
    eslatma = models.BooleanField(default=False, verbose_name="Notified")
    email_sent = models.BooleanField(default=False, verbose_name="Email Sent")
    eslatish_kunlari = models.PositiveIntegerField(default=30, verbose_name="Days Before Notification")
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Status"
    )
    sana = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created Date"
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        verbose_name="Last Updated"
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name="Archived"
    )
    days_left = models.IntegerField(null=True, blank=True, verbose_name="Days Left")
    days_overdue = models.IntegerField(null=True, blank=True, verbose_name="Days Overdue")

    objects = BildirishnomaManager()

    def update_status(self):
        current_date = timezone.now().date()
        days_left = (self.tolov_sana - current_date).days
        paid_for_month = sum(
            t.summa for t in self.chiqim.tolovlar.filter(
                sana__year=self.tolov_sana.year,
                sana__month=self.tolov_sana.month
            )
        )
        monthly_payment = self.chiqim.oyiga_tolov
        is_paid = paid_for_month >= monthly_payment or self.chiqim.qoldiq_summa <= 0

        if is_paid:
            self.status = 'paid'
            self.eslatma = True
        elif days_left < 0:
            self.status = 'overdue'
        elif days_left <= 3:
            self.status = 'urgent'
        elif days_left <= 7:
            self.status = 'warning'
        else:
            self.status = 'pending'

        try:
            eslatish_kunlari = int(self.eslatish_kunlari)
        except (ValueError, TypeError):
            logger.warning(f"Invalid eslatish_kunlari for Notification ID {self.id}: {self.eslatish_kunlari}. Defaulting to 30.")
            eslatish_kunlari = 30
            self.eslatish_kunlari = eslatish_kunlari

        self.eslatma = days_left <= eslatish_kunlari and not is_paid
        self.days_left = days_left
        self.days_overdue = abs(days_left) if days_left < 0 else 0

        if self.status != self._original_status:
            action = "Updated"
            action_emoji = "🔔"
            message = (
                f"<b>{action_emoji} Notification {action}</b>\n"
                f"📋 <u>Notification Details:</u>\n"
                f"  • Buyer: {self.chiqim.xaridor.ism_familiya}\n"
                f"  • Vehicle: <code>{self.chiqim.truck.po_id}</code> ({self.chiqim.truck.make} {self.chiqim.truck.model})\n"
                f"  • Payment Date: {self.tolov_sana}\n"
                f"  • Status: {self.get_status_display()}\n"
                f"  • Days Left: {self.days_left or 0}\n"
                f"  • Days Overdue: {self.days_overdue or 0}\n"
                f"\n👤 <u>Admin:</u>\n"
                f"  • Username: <code>{self.chiqim.xaridor.user.username}</code>\n"
                f"  • Name: {self.chiqim.xaridor.get_user_full_name()}"
            )
            self._original_status = self.status
            super().save(update_fields=['status', 'eslatma', 'days_left', 'days_overdue'])
            send_to_telegram(message)
        else:
            super().save(update_fields=['status', 'eslatma', 'days_left', 'days_overdue'])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_status = getattr(self, 'status', 'pending')

    @property
    def progress_percentage(self):
        if self.chiqim.narx == 0:
            return 0
        return ((self.chiqim.narx - self.chiqim.qoldiq_summa) / self.chiqim.narx) * 100

    @property
    def pending_debt(self):
        if self.status in ['pending', 'warning', 'urgent', 'overdue'] and self.tolov_sana >= timezone.now().date():
            return self.chiqim.oyiga_tolov - sum(
                t.summa for t in self.chiqim.tolovlar.filter(
                    sana__year=self.tolov_sana.year,
                    sana__month=self.tolov_sana.month
                )
            )
        return 0

    @property
    def is_active(self):
        return self.status != 'paid' and self.tolov_sana >= timezone.now().date()

    def __str__(self):
        return f"{self.chiqim.xaridor} - {self.tolov_sana} ({self.get_status_display()})"

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ['tolov_sana']
        indexes = [
            models.Index(fields=['tolov_sana']),
            models.Index(fields=['status']),
        ]

class EmailHistory(models.Model):
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    bildirishnoma = models.ForeignKey(
        Bildirishnoma,
        on_delete=models.CASCADE,
        related_name='email_history',
        verbose_name="Notification"
    )
    subject = models.CharField(
        max_length=255,
        verbose_name="Email Subject"
    )
    message = models.TextField(
        verbose_name="Email Content"
    )
    recipient = models.EmailField(
        verbose_name="Recipient Email"
    )
    sent_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Sent Date"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='success',
        verbose_name="Status"
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name="Error Message"
    )

    def save(self, *args, **kwargs):
        is_new = not self.pk
        super().save(*args, **kwargs)
        if is_new:
            message = (
                f"<b>✉️ Email History Created</b>\n"
                f"📋 <u>Email Details:</u>\n"
                f"  • Subject: {self.subject}\n"
                f"  • Recipient: <code>{self.recipient}</code>\n"
                f"  • Status: {self.get_status_display()}\n"
                f"  • Sent Date: {self.sent_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"  • Error: {self.error_message or 'None'}\n"
                f"\n📄 <u>Notification:</u>\n"
                f"  • Buyer: {self.bildirishnoma.chiqim.xaridor.ism_familiya}\n"
                f"  • Vehicle: <code>{self.bildirishnoma.chiqim.truck.po_id}</code>\n"
                f"\n👤 <u>Admin:</u>\n"
                f"  • Username: <code>{self.bildirishnoma.chiqim.xaridor.user.username}</code>\n"
                f"  • Name: {self.bildirishnoma.chiqim.xaridor.get_user_full_name()}"
            )
            send_to_telegram(message)

    def __str__(self):
        return f"{self.bildirishnoma} - {self.sent_at} ({self.get_status_display()})"

    class Meta:
        verbose_name = "Email History"
        verbose_name_plural = "Email Histories"
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['sent_at']),
            models.Index(fields=['status']),
        ]