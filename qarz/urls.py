from django.urls import path
from . import views

urlpatterns = [
    path('', views.qarz_view, name='qarz_view'),
    path('add/', views.qarz_view, {'action': 'add'}, name='add_qarz'),
    path('update/<int:qarz_id>/', views.qarz_view, {'action': 'update'}, name='update_qarz'),
    path('delete/<int:qarz_id>/', views.qarz_view, {'action': 'delete'}, name='delete_qarz'),
    path('detail/<int:qarz_id>/', views.qarz_detail, name='qarz_detail'),
    path('truck/<int:truck_id>/', views.truck_details, name='truck_details'),
    path('add-payment/<int:qarz_id>/', views.qarz_view, {'action': 'add_payment'}, name='add_payment'),
    path('update-payment/<int:qarz_id>/<int:payment_id>/', views.qarz_view, {'action': 'update_payment'},
         name='update_payment'),
    path('delete-payment/<int:qarz_id>/<int:payment_id>/', views.qarz_view, {'action': 'delete_payment'},
         name='delete_payment'),
]