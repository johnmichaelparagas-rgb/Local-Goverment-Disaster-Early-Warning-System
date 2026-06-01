from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView, TokenRefreshView, TokenVerifyView,
)

from . import views

router = DefaultRouter()
router.register('sensors', views.SensorViewSet, basename='sensor')
router.register('incidents', views.IncidentViewSet, basename='incident')
router.register('hazard-images', views.HazardImageViewSet, basename='hazardimage')
router.register('warnings', views.WarningViewSet, basename='warning')

urlpatterns = [
    # Auth — custom login (returns user profile) + standard JWT token lifecycle
    path('auth/login', views.LoginView.as_view(), name='login'),
    path('auth/me', views.MeView.as_view(), name='me'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('health', views.health, name='health'),

    # Public masked API (mobile / citizen clients)
    path('public/sensors', views.PublicSensorsView.as_view()),
    path('public/warnings', views.PublicWarningsView.as_view()),
    path('public/incidents', views.PublicIncidentsView.as_view()),
    path('public/situation', views.PublicSituationView.as_view()),

    # Secure dashboard API
    path('', include(router.urls)),
]
