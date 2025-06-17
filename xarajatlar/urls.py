
from django.urls import path
from . import views

urlpatterns = [
    path('', views.xarajatlar_list, name='xarajatlar_list'),
    path('add/', views.xarajat_add, name='xarajat_add'),
    path('edit/<int:xarajat_id>/', views.xarajat_edit, name='xarajat_edit'),
    path('delete/<int:xarajat_id>/', views.xarajat_delete, name='xarajat_delete'),

]