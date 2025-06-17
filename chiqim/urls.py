from django.urls import path
from . import views

urlpatterns = [
    path('chiqim/', views.chiqim_list, name='chiqim_list'),
    path('add/', views.chiqim_create, name='chiqim_add'),
    path('edit/<int:id>/', views.chiqim_update, name='chiqim_edit'),
    path('delete/<int:id>/', views.chiqim_delete, name='chiqim_delete'),
    path('detail/<int:id>/', views.chiqim_detail, name='chiqim_detail'),
    path('payment/add/<int:chiqim_id>/', views.add_payment, name='add_payment_chiqim'),
    path('payment/edit/<int:tolov_id>/', views.update_payment, name='update_payment'),
    path('payment/delete/<int:tolov_id>/', views.delete_payment, name='delete_payment'),
    path('bildirishnoma_list/', views.bildirisnoma_list, name='bildirishnomalar'),
    path('bildirishnoma/mark/<int:bildirishnoma_id>/', views.mark_notification, name='mark_notification'),
    path('send-email/<int:bildirishnoma_id>/', views.send_payment_reminder_email, name='send_payment_reminder_email'),
    path('boshlangich_payment/add/<int:chiqim_id>/', views.add_boshlangich_payment, name='add_boshlangich_payment'),
    path('boshlangich_payment/edit/<int:tolov_id>/', views.update_boshlangich_payment, name='update_boshlangich_payment'),
    path('boshlangich_payment/delete/<int:tolov_id>/', views.delete_boshlangich_payment, name='delete_boshlangich_payment'),
    path('bildirishnoma/email-history/<int:bildirishnoma_id>/', views.email_history, name='email_history'),
]