from django.contrib import admin 
from django.urls import path,include 
from . import views 
from .views import update_quantity, run_numb, update_plan

urlpatterns = [
    path('', views.home, name='home'),
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('solutions/', views.solutions_list, name='solutions_list'),
    path('new_order/', views.new_order, name='new_order'),
    path('usage_history/', views.usage_history, name='usage_history'),
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    path('inventory_search/', views.inventory_search, name='inventory_search'),
]

urlpatterns += [
    path('api/update-quantity/', update_quantity, name='api_update_quantity'),
    path('export-usage/', views.export_usage, name='export_usage'),
    path('run-numb/', run_numb, name='run_numb'),
    path('api/update-plan/', update_plan, name='api_update_plan'),
]


