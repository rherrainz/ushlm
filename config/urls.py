from django.contrib import admin
from django.urls import path, include
from market import views
urlpatterns = [
    path('acerca-de/', views.about, name='about'),
    path('admin/', admin.site.urls), path('cuenta/', include('django.contrib.auth.urls')),
    path('registro/', views.signup, name='signup'), path('', views.catalog, name='catalog'),
    path('ofertas/<int:pk>/', views.detail, name='detail'), path('ofertas/<int:pk>/solicitar/', views.book, name='book'),
    path('mis-solicitudes/', views.bookings, name='bookings'), path('prestador/', views.dashboard, name='dashboard'),
    path('prestador/nueva/', views.edit_offer, name='new_offer'), path('prestador/ofertas/<int:pk>/', views.edit_offer, name='edit_offer'),
    path('prestador/ofertas/<int:pk>/inventario/', views.inventory, name='inventory'),
    path('solicitudes/<int:pk>/<str:action>/', views.action, name='action'),
]
