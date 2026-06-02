from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import TemplateView

from core import web_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),

    # Server-rendered management UI (session auth, inline formsets, django-filter)
    path('login/', auth_views.LoginView.as_view(template_name='manage/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('manage/', web_views.dashboard, name='manage-dashboard'),
    path('manage/incidents/new/', web_views.incident_create, name='manage-incident-create'),
    path('manage/incidents/<int:pk>/edit/', web_views.incident_edit, name='manage-incident-edit'),

    # Public landing page (marketing / live public situation snapshot).
    path('', TemplateView.as_view(template_name='index.html'), name='home'),

    # SEO: robots + sitemap (rendered with the request for absolute URLs).
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'), name='robots'),
    path('sitemap.xml', TemplateView.as_view(template_name='sitemap.xml', content_type='application/xml'), name='sitemap'),

    # JWT single-page monitoring dashboard (auth handled client-side).
    path('dashboard/', TemplateView.as_view(template_name='dashboard.html'), name='dashboard'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
