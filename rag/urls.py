from django.urls import path
from .views import *

urlpatterns = [
    # Frontend HTML templates
    path("", HomeView.as_view(), name="home"),
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("conversations/<int:conversation_id>/", ConversationDetailView.as_view(), name="conversation-detail"),

    # Backend Secure APIs JSON Payloads
    path("api/register/", RegisterAPIView.as_view(), name="api-register"),
    path("api/login/", LoginAPIView.as_view(), name="api-login"),
    path("api/dashboard-metrics/", DashboardMetricsAPIView.as_view(), name="api-dashboard-metrics"),
    path("api/documents/", DocumentUploadAPIView.as_view(), name="api-document-upload"),
    path("api/query/", QueryAPIView.as_view(), name="api-query"),
    path("api/conversations/", ConversationAPIView.as_view(), name="api-conversation-list"),
    path("api/conversations/<int:conversation_id>/", ConversationDetailAPIView.as_view(), name="api-conversation-detail"),
    path("api/conversations/<int:conversation_id>/messages/", ConversationMessageAPIView.as_view(), name="api-conversation-messages"),
    path("api/conversations/<int:conversation_id>/messages/<int:message_id>/", ConversationMessageDetailAPIView.as_view(), name="api-conversation-message-detail"),
]