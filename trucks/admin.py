from django.contrib import admin
from .models import Truck

@admin.register(Truck)
class TruckAdmin(admin.ModelAdmin):
    list_display = ('make', 'model', 'year', 'price', 'location', 'purchase_date', 'created_date')
    list_filter = ('location', 'year', 'created_date')
    search_fields = ('make', 'model', 'company')

