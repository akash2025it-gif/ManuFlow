from django.urls import path
from . import views

urlpatterns = [
    # Production Central Hub & Observatory
    path('', views.production_dashboard_view, name='production_hub'),

    # Production Runs / Work Orders
    path('runs/', views.production_run_list_view, name='production_run_list'),
    path('runs/create/', views.production_run_create_view, name='production_run_create'),
    path('runs/<int:pk>/', views.production_run_detail_view, name='production_run_detail'),
    path('runs/<int:pk>/execute/', views.production_run_execute_view, name='production_run_execute'),
    path('runs/<int:pk>/post/', views.production_run_post_view, name='production_run_post'),

    # Variance Intelligence & Production Reports
    path('reports/', views.production_reports_view, name='production_reports'),
]
