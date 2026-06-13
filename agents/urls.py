# agents/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Page views
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_page, name='login_page'),
    path('signup/', views.signup_page, name='signup_page'),
    
    # Authentication API
    path('api/register/', views.register, name='register'),
    path('api/signin/', views.signin, name='signin'),
    path('api/signout/', views.signout, name='signout'),
    path('api/check-auth/', views.check_auth, name='check_auth'),
    
    # Agent management
    path('api/agents/', views.get_agents, name='get_agents'),
    path('api/agents/create/', views.create_agent, name='create_agent'),
    path('api/agents/delete/', views.delete_agent, name='delete_agent'),
    
    # Chat and memory
    path('api/chat/', views.chat, name='chat'),
    path('api/memory/add/', views.add_memory_view, name='add_memory'),
    path('api/memories/<int:agent_id>/', views.get_memories, name='get_memories'),
    path('api/conversations/<int:agent_id>/', views.get_conversations, name='get_conversations'),
    
    # Agent-to-agent conversation (with conclusion)
    path('api/agent-conversation/', views.agent_conversation, name='agent_conversation'),
    
    # Web search endpoint
    path('api/search/', views.search_only, name='search_only'),
    
    # Agent summary and management
    path('api/agent-summary/<int:agent_id>/', views.agent_summary, name='agent_summary'),
    path('api/agent/update-name/', views.update_agent_name, name='update_agent_name'),
]