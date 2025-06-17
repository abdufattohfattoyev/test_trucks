from django.urls import path
from . import views

urlpatterns = [
    path('', views.xaridorlar_list, name='xaridorlar_list'),
    path('add/', views.xaridor_add, name='xaridor_add'),
    path('edit/<int:id>/', views.xaridor_edit, name='edit_xaridor'),
    path('delete/<int:id>/', views.xaridor_delete, name='xaridor_delete'),
    path('passport/<int:id>/', views.view_passport, name='view_passport'),
    path('hujjat/delete/<int:hujjat_id>/', views.delete_hujjat, name='delete_hujjat'),
    path('hujjat/upload/', views.upload_hujjat, name='upload_hujjat'),
]