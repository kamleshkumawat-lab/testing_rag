from django.contrib.auth.models import User

from rest_framework import serializers

from .models import *

class RegisterSerializer(serializers.ModelSerializer):

    password = serializers.CharField(
        write_only=True,
        min_length=6,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "password",
        )

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )
    
class DocumentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Document
        fields = (
            "id",
            "title",
            "raw_text",
            "metadata",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        )

class DocumentChunkSerializer(serializers.ModelSerializer):

    class Meta:
        model = DocumentChunk
        fields = (
            "id",
            "document",
            "chunk_index",
            "content",
            "metadata",
            "created_at",
        )

        read_only_fields = (
            "id",
            "created_at",
        )

class ConversationSerializer(serializers.ModelSerializer):

    message_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id",
            "title",
            "message_count",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
        )

    def get_message_count(self, obj):
        return obj.messages.count()
    

class ConversationMessageSerializer(serializers.ModelSerializer):

    class Meta:
        model = ConversationMessage
        fields = (
            "id",
            "conversation",
            "role",
            "content",
            "metadata",
            "created_at",
        )

        read_only_fields = (
            "id",
            "conversation",
            "role",
            "metadata",
            "created_at",
        )

class QuerySerializer(serializers.Serializer):

    question = serializers.CharField()

    top_k = serializers.IntegerField(
        default=5,
        min_value=1,
        max_value=20,
    )