from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('espace/<slug:slug>/', views.espace, name='espace'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('forgot/1/', views.reset_step1, name='reset_step1'),
    path('forgot/2/', views.reset_step2, name='reset_step2'),
    path('forgot/3/', views.reset_step3, name='reset_step3'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/read/', views.notifications_read, name='notifications_read'),
    path('notifications/poll/', views.notifications_poll, name='notifications_poll'),
    path('users/', views.user_list, name='user_list'),
    path('users/add/', views.user_add, name='user_add'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),
]
