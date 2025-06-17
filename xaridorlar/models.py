from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, FileExtensionValidator, EmailValidator
from django.utils.text import slugify
import os
from phonenumber_field.modelfields import PhoneNumberField
from django.core.exceptions import ValidationError
from django.conf import settings
from .utils import send_to_telegram, send_file_to_telegram
from typing import Optional

def generate_unique_filename(instance, filename):
    """Generate a filename preserving the original name, with a suffix if needed."""
    base, ext = os.path.splitext(filename)
    slug = slugify(base)
    new_filename = f"{slug}{ext}"
    upload_dir = 'xaridor_hujjatlar/'
    full_path = os.path.join(upload_dir, new_filename)

    counter = 1
    while os.path.exists(os.path.join(settings.MEDIA_ROOT, full_path)):
        new_filename = f"{slug}_{counter}{ext}"
        full_path = os.path.join(upload_dir, new_filename)
        counter += 1

    return full_path

def validate_file_size(value):
    """File size validator (10MB limit)."""
    limit = 10 * 1024 * 1024  # 10MB in bytes
    if value.size > limit:
        raise ValidationError("File size must be less than 10MB.")

class Xaridor(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='xaridorlar',
        verbose_name="User"
    )
    ism_familiya = models.CharField(
        max_length=100,
        verbose_name="Ism va Familiya"
    )
    telefon_raqam = PhoneNumberField(
        blank=True,
        null=True,
        verbose_name="Telefon Raqami",
        help_text="Masalan: +998901234567"
    )
    email = models.EmailField(
        blank=True,
        null=True,
        validators=[EmailValidator()],
        verbose_name="Email Manzili",
        help_text="Masalan: example@domain.com"
    )
    hozirgi_balans = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Hozirgi Balans",
        blank=True
    )
    sana = models.DateField(verbose_name="Sana")
    izoh = models.TextField(
        verbose_name="Izoh",
        blank=True,
        null=True
    )
    created_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Yaratilgan Sana"
    )

    def get_user_full_name(self) -> str:
        """Foydalanuvchi to‘liq ismini qaytarish."""
        full_name = f"{self.user.first_name} {self.user.last_name}".strip()
        return full_name or self.user.username

    def update_financials(self):
        """Hozirgi balansni yangilash."""
        from chiqim.models import Chiqim
        total_debt = Chiqim.objects.filter(xaridor=self).aggregate(total=models.Sum('qoldiq_summa'))['total'] or 0
        self.hozirgi_balans = total_debt
        self.save(update_fields=['hozirgi_balans'], skip_telegram=True)

    @property
    def total_debt(self):
        """Umumiy qarzni hisoblash."""
        from chiqim.models import Chiqim
        return Chiqim.objects.filter(xaridor=self).aggregate(total=models.Sum('qoldiq_summa'))['total'] or 0

    def save(self, *args, skip_telegram=False, **kwargs):
        is_new = not self.pk
        old_instance = None

        # Agar ob'ekt mavjud bo‘lsa, eski ma'lumotlarni olish
        if not is_new:
            try:
                old_instance = Xaridor.objects.get(pk=self.pk)
            except Xaridor.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        # Telegram xabarini faqat kerakli holatlarda yuborish
        if not skip_telegram:
            # Muhim maydonlar o‘zgarganini tekshirish
            significant_change = is_new or (
                old_instance and (
                    old_instance.ism_familiya != self.ism_familiya or
                    old_instance.telefon_raqam != self.telefon_raqam or
                    old_instance.email != self.email or
                    old_instance.sana != self.sana or
                    old_instance.izoh != self.izoh
                )
            )

            if significant_change:
                action = "Yaratildi" if is_new else "Yangilandi"
                action_emoji = "👤" if is_new else "🔄"
                izoh = self.izoh[:500] + '...' if self.izoh and len(self.izoh) > 500 else self.izoh or 'Yo‘q'
                telefon = f"{self.telefon_raqam}" if self.telefon_raqam else "Yo‘q"
                email = self.email or "Yo‘q"
                message = (
                    f"<b>{action_emoji} Xaridor {action}</b>\n"
                    f"📋 <u>Xaridor ma'lumotlari:</u>\n"
                    f"  • Ism va Familiya: {self.ism_familiya}\n"
                    f"  • Telefon Raqami: <code>{telefon}</code>\n"
                    f"  • Email: <code>{email}</code>\n"
                    f"  • Hozirgi Balans: ${self.hozirgi_balans:,.2f}\n"
                    f"  • Sana: {self.sana}\n"
                    f"  • Izoh: {izoh}\n"
                    f"\n👤 <u>Admin:</u>\n"
                    f"  • Username: <code>{self.user.username}</code>\n"
                    f"  • Ism: {self.get_user_full_name()}"
                )
                send_to_telegram(message)

    def delete(self, *args, **kwargs):
        # Telegram xabarini tayyorlash
        telefon = f"{self.telefon_raqam}" if self.telefon_raqam else "Yo‘q"
        email = self.email or "Yo‘q"
        message = (
            f"<b>🗑️ Xaridor O‘chirildi</b>\n"
            f"📋 <u>Xaridor ma'lumotlari:</u>\n"
            f"  • Ism va Familiya: {self.ism_familiya}\n"
            f"  • Telefon Raqami: <code>{telefon}</code>\n"
            f"  • Email: <code>{email}</code>\n"
            f"  • Hozirgi Balans: ${self.hozirgi_balans:,.2f}\n"
            f"\n👤 <u>Admin:</u>\n"
            f"  • Username: <code>{self.user.username}</code>\n"
            f"  • Ism: {self.get_user_full_name()}"
        )
        super().delete(*args, **kwargs)
        send_to_telegram(message)

    def __str__(self):
        return f"{self.ism_familiya} - {self.user.username}"

    class Meta:
        verbose_name = "Xaridor"
        verbose_name_plural = "Xaridorlar"
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['ism_familiya']),
            models.Index(fields=['email']),
        ]

class XaridorHujjat(models.Model):
    xaridor = models.ForeignKey(
        Xaridor,
        on_delete=models.CASCADE,
        related_name='hujjatlar',
        verbose_name="Xaridor"
    )
    hujjat = models.FileField(
        upload_to=generate_unique_filename,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']),
            validate_file_size
        ],
        verbose_name="Hujjat Fayli"
    )
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Asl Fayl Nomi"
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Yuklangan Sana"
    )

    def save(self, *args, **kwargs):
        is_new = not self.pk
        old_instance = None

        # Agar ob'ekt mavjud bo‘lsa, eski ma'lumotlarni olish
        if not is_new:
            try:
                old_instance = XaridorHujjat.objects.get(pk=self.pk)
            except XaridorHujjat.DoesNotExist:
                pass

        if self.hujjat and not self.original_filename:
            self.original_filename = os.path.basename(self.hujjat.name)
        super().save(*args, **kwargs)

        # Telegram xabarini faqat kerakli holatlarda yuborish
        significant_change = is_new or (
            old_instance and old_instance.hujjat.name != self.hujjat.name
        )

        if significant_change:
            action = "Yaratildi" if is_new else "Yangilandi"
            action_emoji = "📎" if is_new else "🔄"
            telefon = f"{self.xaridor.telefon_raqam}" if self.xaridor.telefon_raqam else "Yo‘q"
            message = (
                f"<b>{action_emoji} Xaridor Hujjati {action}</b>\n"
                f"📋 <u>Hujjat ma'lumotlari:</u>\n"
                f"  • Fayl Nomi: <code>{self.original_filename}</code>\n"
                f"  • Yuklangan Sana: {self.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"\n👥 <u>Xaridor:</u>\n"
                f"  • Ism va Familiya: {self.xaridor.ism_familiya}\n"
                f"  • Telefon Raqami: <code>{telefon}</code>\n"
                f"\n👤 <u>Admin:</u>\n"
                f"  • Username: <code>{self.xaridor.user.username}</code>\n"
                f"  • Ism: {self.xaridor.get_user_full_name()}"
            )
            send_to_telegram(message)

            # Hujjat faylini yuborish
            file_path = self.hujjat.path
            original_filename = self.original_filename or os.path.basename(self.hujjat.name)
            caption = (
                f"<b>📎 Xaridor Hujjati</b>\n"
                f"Xaridor: {self.xaridor.ism_familiya}\n"
                f"Telefon Raqami: <code>{telefon}</code>\n"
                f"Fayl: <code>{original_filename}</code>"
            )
            send_file_to_telegram(file_path, original_filename, caption)

    def delete(self, *args, **kwargs):
        # Telegram xabarini tayyorlash
        telefon = f"{self.xaridor.telefon_raqam}" if self.xaridor.telefon_raqam else "Yo‘q"
        message = (
            f"<b>🗑️ Xaridor Hujjati O‘chirildi</b>\n"
            f"📋 <u>Hujjat ma'lumotlari:</u>\n"
            f"  • Fayl Nomi: <code>{self.original_filename}</code>\n"
            f"\n👥 <u>Xaridor:</u>\n"
            f"  • Ism va Familiya: {self.xaridor.ism_familiya}\n"
            f"  • Telefon Raqami: <code>{telefon}</code>\n"
            f"\n👤 <u>Admin:</u>\n"
            f"  • Username: <code>{self.xaridor.user.username}</code>\n"
            f"  • Ism: {self.xaridor.get_user_full_name()}"
        )
        super().delete(*args, **kwargs)
        send_to_telegram(message)

    def __str__(self):
        return f"{self.xaridor.ism_familiya} - {self.original_filename or os.path.basename(self.hujjat.name)}"

    class Meta:
        verbose_name = "Xaridor Hujjati"
        verbose_name_plural = "Xaridor Hujjatlari"
        indexes = [
            models.Index(fields=['xaridor']),
        ]