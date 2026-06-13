# agents/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Agent(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('idle', 'Idle'),
        ('busy', 'Busy'),
        ('offline', 'Offline'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agents')
    name = models.CharField(max_length=100)
    age = models.IntegerField(default=30)
    traits = models.CharField(max_length=500, help_text="Comma-separated personality traits")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    description = models.TextField(blank=True, default='')
    avatar = models.CharField(max_length=50, default='fas fa-robot')
    color = models.CharField(max_length=100, default='from-cyan-500-to-teal-500')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    system_prompt_extra = models.TextField(blank=True, default='')
    model_temperature = models.FloatField(default=0.7)
    max_tokens = models.IntegerField(default=1500)

    class Meta:
        unique_together = ['user', 'name']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.user.email})"
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "traits": self.traits,
            "status": self.status,
            "description": self.description,
            "avatar": self.avatar,
            "color": self.color,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Memory(models.Model):
    MEMORY_TYPES = [
        ('conversation', 'Conversation'),
        ('fact', 'Fact'),
        ('preference', 'Preference'),
        ('custom', 'Custom'),
    ]

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='memories')
    memory_text = models.TextField()
    memory_type = models.CharField(max_length=20, choices=MEMORY_TYPES, default='conversation')
    importance = models.FloatField(default=0.5)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.agent.name}: {self.memory_text[:50]}"
    
    def to_dict(self):
        return {
            "id": self.id,
            "memory_text": self.memory_text,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class Conversation(models.Model):
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='conversations')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.agent.name} - {self.created_at.date()}"


class Message(models.Model):
    SENDER_TYPES = [
        ('user', 'User'),
        ('agent', 'Agent'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender_type = models.CharField(max_length=10, choices=SENDER_TYPES)
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.sender_type}: {self.content[:50]}"


class AgentConversation(models.Model):
    agent1 = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='as_agent1')
    agent2 = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='as_agent2')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agent_conversations')
    topic = models.CharField(max_length=500)
    log = models.JSONField(default=list)
    conclusion = models.TextField(blank=True, null=True)  # Add this field
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.agent1.name} ↔ {self.agent2.name}"