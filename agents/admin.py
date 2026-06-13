# agents/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Agent, Conversation, Message, Memory, AgentConversation

# Unregister the default User admin first
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

# Register custom User admin (using Django's User model)
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active']
    list_filter = ['is_staff', 'is_active', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {'fields': ()}),
    )


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'status', 'created_at']
    search_fields = ['name', 'user__email', 'user__username']
    list_filter = ['status', 'created_at']


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'agent', 'user', 'created_at']
    search_fields = ['agent__name', 'user__email']
    list_filter = ['created_at']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'sender_type', 'timestamp']
    search_fields = ['content']
    list_filter = ['sender_type', 'timestamp']


@admin.register(Memory)
class MemoryAdmin(admin.ModelAdmin):
    list_display = ['agent', 'memory_type', 'importance', 'timestamp']
    search_fields = ['agent__name', 'memory_text']
    list_filter = ['memory_type', 'importance', 'timestamp']


@admin.register(AgentConversation)
class AgentConversationAdmin(admin.ModelAdmin):
    list_display = ['agent1', 'agent2', 'user', 'created_at']
    search_fields = ['agent1__name', 'agent2__name', 'user__email']
    list_filter = ['created_at']