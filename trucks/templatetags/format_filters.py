from django import template

register = template.Library()

@register.filter
def format_number(value):
    try:
        # Qiymatni float yoki int ga aylantiramiz
        num = float(value)
        # Butun qismni ajratib olamiz
        int_part = int(num)
        # 3 ta raqamdan bo'lib, bo'sh joy qo'shamiz
        int_part_str = f"{int_part:,}".replace(',', ' ')
        # Agar son o'nlik bo'lsa, o'nlik qismini qo'shamiz
        if num != int_part:
            decimal_part = f"{num:.2f}".split('.')[1]
            return f"{int_part_str}.{decimal_part}"
        return int_part_str
    except (ValueError, TypeError):
        return value