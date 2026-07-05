from django.shortcuts import get_object_or_404, render
from django.contrib.auth import authenticate
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Document, Conversation, ConversationMessage
from .tasks import process_document
from .serializers import RegisterSerializer, DocumentSerializer, ConversationSerializer, ConversationMessageSerializer
from .services import RAGService , TextToSQLService
from rest_framework.test import APITestCase
from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth.models import User



# ====================================================
# 1. FRONTEND TEMPLATE VIEWS (Render HTML Only)
# ====================================================

class HomeView(View):
    def get(self, request):
        return render(request, "index.html")

class RegisterView(View):
    def get(self, request):
        return render(request, "register.html")

class LoginView(View):
    def get(self, request):
        return render(request, "login.html")

class DashboardView(View):
    # FIXED: Crash se bachane ke liye standard rendering view banaya.
    # Ab data automatic JavaScript `localStorage` token se secure API call ke through aayega.
    def get(self, request):
        return render(request, "dashboard.html")

class ConversationDetailView(View):
    def get(self, request, conversation_id):
        return render(request, "chat.html", {"conversation_id": conversation_id})


# ====================================================
# 2. BACKEND API ENDPOINTS (Returns JSON Data Only)
# ====================================================

class RegisterAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                "success": True,
                "message": "User registered successfully.",
                "data": {
                    "id": user.id,
                    "username": user.username,
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                }
            }, status=status.HTTP_201_CREATED)
        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        
        user = authenticate(username=username, password=password)
        if user is None:
            return Response({"success": False, "message": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
            
        refresh = RefreshToken.for_user(user)
        return Response({
            "success": True,
            "message": "Login successful.",
            "data": {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            }
        }, status=status.HTTP_200_OK)


class DashboardMetricsAPIView(APIView):
    # NEW: Secure backend data processor endpoint
    permission_classes = [IsAuthenticated]

    def get(self, request):
        documents = Document.objects.filter(created_by=request.user).order_by("-created_at")
        conversations = Conversation.objects.filter(user=request.user).order_by("-updated_at")

        doc_serializer = DocumentSerializer(documents, many=True)
        conv_serializer = ConversationSerializer(conversations, many=True)

        return Response({
            "success": True,
            "metrics": {
                "total_documents": documents.count(),
                "completed_documents": documents.filter(status=Document.Status.COMPLETED).count(),
                "processing_documents": documents.filter(status=Document.Status.PROCESSING).count(),
                "pending_documents": documents.filter(status=Document.Status.PENDING).count(),
            },
            "documents": doc_serializer.data,
            "conversations": conv_serializer.data
        }, status=status.HTTP_200_OK)


class DocumentUploadAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = DocumentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        document = serializer.save(created_by=request.user, status=Document.Status.PENDING)
        print("Document uploaded with ID:", document.id, "and status:", document.status)
        process_document.apply_async(args=[document.id], countdown=10)
        print("Celery task for document processing has been queued for document ID:", document.id)

        return Response({
            "success": True,
            "message": "Document uploaded successfully.",
            "data": DocumentSerializer(document).data,
        }, status=status.HTTP_201_CREATED)
    

class QueryAPIView(APIView):
    """
    API to query the RAG service.
    """

    def post(self, request):
        question = request.data.get("question")

        if not question:
            return Response(
                {
                    "success": False,
                    "message": "Question is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            rag_service = RAGService()

            response = rag_service.generate_response(question=question)

            return Response(
                {
                    "success": True,
                    "message": "Response generated successfully.",
                    "data": response,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "message": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class ConversationAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        conversations = Conversation.objects.filter(user=request.user).order_by("-updated_at")
        serializer = ConversationSerializer(conversations, many=True)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request):
        title = request.data.get("title", "New Chat")
        conversation = Conversation.objects.create(user=request.user, title=title)
        serializer = ConversationSerializer(conversation)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_201_CREATED)
    

class ConversationDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def get_object(self, conversation_id, user):
        return get_object_or_404(Conversation, id=conversation_id, user=user)

    def get(self, request, conversation_id):
        conversation = self.get_object(conversation_id, request.user)
        serializer = ConversationSerializer(conversation)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_200_OK)

    def patch(self, request, conversation_id):
        conversation = self.get_object(conversation_id, request.user)
        title = request.data.get("title")
        if not title:
            return Response({"success": False, "message": "title is required."}, status=status.HTTP_400_BAD_REQUEST)
        conversation.title = title
        conversation.save()
        return Response({"success": True, "data": ConversationSerializer(conversation).data}, status=status.HTTP_200_OK)

    def delete(self, request, conversation_id):
        conversation = self.get_object(conversation_id, request.user)
        conversation.delete()
        return Response({"success": True, "message": "Conversation deleted successfully."}, status=status.HTTP_200_OK)
    
class ConversationMessageAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_conversation(self, conversation_id, user):
        return get_object_or_404(Conversation, id=conversation_id, user=user)

    def get(self, request, conversation_id):
        conversation = self.get_conversation(conversation_id, request.user)
        messages = ConversationMessage.objects.filter(conversation=conversation).order_by("created_at")
        serializer = ConversationMessageSerializer(messages, many=True)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request, conversation_id):

        conversation = self.get_conversation(
            conversation_id,
            request.user,
        )

        question = request.data.get("question")

        if not question:
            return Response(
                {
                    "success": False,
                    "message": "question is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save user message
        user_message = ConversationMessage.objects.create(
            conversation=conversation,
            role=ConversationMessage.Role.USER,
            content=question,
        )

        # Auto rename conversation
        if (
            conversation.title == "New Chat"
            and conversation.messages.filter(
                role=ConversationMessage.Role.USER
            ).count() == 1
        ):
            conversation.title = (
                question[:50] + "..."
                if len(question) > 50
                else question
            )

            conversation.save(update_fields=["title"])

        try:

            text_sql = TextToSQLService()

            # -----------------------------
            # Text To SQL
            # -----------------------------
            if text_sql.can_handle(question):

                result = text_sql.execute(
                    conversation=conversation,
                    question=question,
                )

                assistant_message = ConversationMessage.objects.create(
                    conversation=conversation,
                    role=ConversationMessage.Role.ASSISTANT,
                    content=result["answer"],
                    metadata={
                        "type": "text_to_sql",
                    },
                )

                sources = result.get("sources", [])

            # -----------------------------
            # RAG
            # -----------------------------
            else:

                rag_service = RAGService()

                result = rag_service.generate_response(
                    conversation=conversation,
                    question=question,
                )

                assistant_message = result["assistant_message"]

                sources = result["sources"]

            return Response(
                {
                    "success": True,
                    "message": "Response generated successfully.",
                    "data": {
                        "conversation_id": conversation.id,
                        "conversation_title": conversation.title,
                        "user_message": ConversationMessageSerializer(
                            user_message
                        ).data,
                        "assistant_message": ConversationMessageSerializer(
                            assistant_message
                        ).data,
                        "sources": sources,
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as exc:

            return Response(
                {
                    "success": False,
                    "message": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        
    

class ConversationMessageDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, conversation_id, message_id):
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
        message = get_object_or_404(ConversationMessage, id=message_id, conversation=conversation)
        return Response({"success": True, "data": ConversationMessageSerializer(message).data}, status=status.HTTP_200_OK)

    def delete(self, request, conversation_id, message_id):
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
        message = get_object_or_404(ConversationMessage, id=message_id, conversation=conversation)
        message.delete()
        return Response({"success": True, "message": "Message deleted successfully."}, status=status.HTTP_200_OK)
    

    
class RAGAPITestCase(APITestCase):

    def setUp(self):

        self.user = User.objects.create_user(
            username="testuser",
            password="test123",
        )

        login_response = self.client.post(
            reverse("login"),
            {
                "username": "testuser",
                "password": "test123",
            },
            format="json",
        )

        self.token = login_response.data["data"]["access"]

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )

    @patch("rag.tasks.process_document.delay")
    def test_document_upload(
        self,
        mock_task,
    ):

        payload = {
            "title": "SEO Guide",
            "raw_text": (
                "SEO is the process of improving "
                "website visibility."
            ),
        }

        response = self.client.post(
            reverse("document-upload"),
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertTrue(
            Document.objects.filter(
                title="SEO Guide"
            ).exists()
        )

        mock_task.assert_called_once()

    @patch("rag.services.RAGService.generate_response")
    def test_query_endpoint(
        self,
        mock_generate,
    ):

        conversation = Conversation.objects.create(
            user=self.user,
            title="New Chat",
        )

        mock_generate.return_value = {
            "answer": "SEO improves website ranking.",
            "assistant_message": None,
            "sources": [],
        }

        response = self.client.post(
            reverse(
                "conversation-message",
                kwargs={
                    "conversation_id": conversation.id,
                },
            ),
            {
                "question": "What is SEO?"
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertTrue(
            response.data["success"]
        )