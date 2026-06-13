import json
import os
import random
import traceback
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.utils import timezone
from langchain_openai import ChatOpenAI
from tavily import TavilyClient
from .models import Agent, Memory, Conversation, Message, AgentConversation
from dotenv import load_dotenv
load_dotenv()
# ============= API KEY AND CONFIGURATION =============
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Tavily API Key (your provided key)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Initialize Tavily client
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

# Initialize LLM
LLM = ChatOpenAI(
    model="gpt-4o-mini",
    max_tokens=1500,
    temperature=0.7,
    api_key=OPENAI_API_KEY
)
# ===========================================================

# ============= TAVILY SEARCH WITH SOURCES =============

def search_web_with_sources(query, max_results=5):
    """
    Search the web using Tavily API and return results with source URLs.
    This shows exactly which websites provided the information.
    """
    try:
        # Perform search with Tavily
        response = tavily_client.search(
            query=query,
            search_depth="advanced",  # "basic" is faster, "advanced" is more thorough
            max_results=max_results,
            include_answer=True,  # Get AI-generated answer
            include_raw_content=False,  # Set to True for full page content
            include_domains=[]
        )
        
        # Extract sources with URLs and content snippets
        sources = []
        for result in response.get('results', []):
            sources.append({
                'url': result.get('url'),
                'title': result.get('title'),
                'content': result.get('content', '')[:500],  # First 500 chars
                'score': result.get('score', 0)
            })
        
        # Also get the answer from Tavily
        tavily_answer = response.get('answer', '')
        
        return {
            'success': True,
            'answer': tavily_answer,
            'sources': sources,
            'query': query
        }
        
    except Exception as e:
        print(f"Tavily search error: {e}")
        return {
            'success': False,
            'error': str(e),
            'sources': []
        }

def generate_response_with_web_search(agent, user, user_message):
    """
    Generate response using web search with source attribution.
    Shows exactly which websites provided the information.
    """
    user_name = user.first_name if user.first_name else user.username.split('@')[0]
    
    # First, search the web for relevant information
    search_result = search_web_with_sources(user_message, max_results=5)
    
    # Get agent memories
    recent_memories = get_agent_memories(agent, limit=5)
    memories_text = "\n".join([f"- {m.memory_text}" for m in recent_memories]) if recent_memories else "No memories yet."
    
    # Get conversation history
    history = get_chat_history(agent, user, limit=10)
    history_text = "\n".join(history) if history else "No previous conversation."
    
    # Build context from search results with sources
    sources_text = ""
    sources_list = []
    
    if search_result['success'] and search_result.get('sources'):
        for i, source in enumerate(search_result['sources'], 1):
            sources_text += f"\nSOURCE {i} - {source['title']}\nURL: {source['url']}\nExcerpt: {source['content']}\n"
            sources_list.append({
                'url': source['url'],
                'title': source['title'],
                'content': source['content'][:200]
            })
    
    # Build the prompt with web search results
    prompt = f"""
You are {agent.name}, age {agent.age}.
Your traits: {agent.traits}
Your status: {agent.status}
Description: {agent.description}

Recent memories:
{memories_text}

Conversation history:
{history_text}

===== WEB SEARCH RESULTS (with real sources) =====
{ sources_text if sources_text else "No web search results available."}

Tavily's suggested answer (use as reference):
{search_result.get('answer', 'No suggested answer.')}

User ({user_name}) asks: {user_message}

IMPORTANT INSTRUCTIONS:
1. Answer the user's question using the web search results above
2. You MUST cite your sources by mentioning the website names or URLs
3. Example: "According to Wikipedia (https://wikipedia.org), ..."
4. If multiple sources have information, mention them all
5. Be conversational but accurate and informative
6. Respond in under 200 words
7. Show your personality as {agent.name}
8. At the end of your response, list the sources you used

Your response:
"""
    
    try:
        response = LLM.invoke(prompt)
        response_text = response.content
        
        # Add a formatted sources section if not already there
        if sources_list and "Source" not in response_text and "source" not in response_text:
            response_text += "\n\n📚 **Sources:**\n"
            for source in sources_list[:3]:
                response_text += f"• [{source['title']}]({source['url']})\n"
        
        # Save memory of the search
        if sources_list:
            source_urls = ", ".join([s['url'] for s in sources_list[:3]])
            add_memory(agent, f"User asked: {user_message[:100]}. Information retrieved from: {source_urls}", 'conversation', 0.5)
        else:
            add_memory(agent, f"Conversation with {user_name} about: {user_message[:50]} (no web search results)", 'conversation', 0.3)
        
        save_message(agent, user, user_message, response_text)
        
        return {
            'response': response_text,
            'sources': sources_list,
            'search_performed': search_result['success']
        }
        
    except Exception as e:
        print(f"Chat error: {e}")
        error_response = f"Hi {user_name}! As {agent.name}, I tried to search for information about '{user_message}' but encountered an issue. Could you please rephrase your question?"
        
        save_message(agent, user, user_message, error_response)
        
        return {
            'response': error_response,
            'sources': [],
            'search_performed': False
        }

# ============= HELPER FUNCTIONS =============

def get_random_color():
    colors = [
        "from-cyan-500-to-blue-500",
        "from-teal-500-to-emerald-500",
        "from-indigo-500-to-purple-500",
        "from-rose-500-to-pink-500",
        "from-amber-500-to-orange-500",
        "from-violet-500-to-fuchsia-500"
    ]
    return random.choice(colors)

def add_memory(agent, memory_text, memory_type='conversation', importance=0.5):
    """Add memory to agent"""
    Memory.objects.create(
        agent=agent,
        memory_text=memory_text,
        memory_type=memory_type,
        importance=importance,
        timestamp=timezone.now()
    )

def get_agent_memories(agent, limit=10):
    """Get recent memories for agent"""
    return list(agent.memories.all().order_by('-timestamp')[:limit])

def get_chat_history(agent, user, limit=20):
    """Get recent conversation history between agent and user"""
    conversations = Conversation.objects.filter(agent=agent, user=user).order_by('-updated_at')
    if conversations.exists():
        latest_conv = conversations.first()
        messages = latest_conv.messages.all().order_by('-timestamp')[:limit]
        history = []
        for msg in reversed(messages):
            sender = "You" if msg.sender_type == 'user' else agent.name
            history.append(f"{sender}: {msg.content}")
        return history
    return []

def save_message(agent, user, user_message, agent_response):
    """Save conversation to database"""
    conversation, created = Conversation.objects.get_or_create(
        agent=agent,
        user=user,
        defaults={'title': user_message[:50]}
    )
    
    Message.objects.create(
        conversation=conversation,
        sender_type='user',
        content=user_message
    )
    
    Message.objects.create(
        conversation=conversation,
        sender_type='agent',
        content=agent_response
    )
    
    conversation.updated_at = timezone.now()
    conversation.save()
    return conversation

def generate_response_without_search(agent, user, user_message):
    """Generate response from agent using LLM without web search (fallback)"""
    user_name = user.first_name if user.first_name else user.username.split('@')[0]
    
    recent_memories = get_agent_memories(agent, limit=10)
    memories_text = "\n".join([f"- {m.memory_text}" for m in recent_memories]) if recent_memories else "No memories yet."
    
    history = get_chat_history(agent, user, limit=20)
    history_text = "\n".join(history) if history else "No previous conversation."
    
    prompt = f"""
    You are {agent.name}, age {agent.age}.
    Your traits: {agent.traits}
    Your status: {agent.status}
    Description: {agent.description}
    
    Recent memories:
    {memories_text}
    
    Conversation history:
    {history_text}
    
    {user_name} says: {user_message}
    
    Respond naturally as {agent.name} in under 150 words. Be conversational and engaging!
    """
    
    try:
        response = LLM.invoke(prompt)
        response_text = response.content
    except Exception as e:
        print(f"Chat error: {e}")
        response_text = f"Hi {user_name}! As {agent.name}, I appreciate your question. I'm {agent.age} years old. What would you like to know?"
    
    add_memory(agent, f"Conversation with {user_name} about: {user_message[:50]}", 'conversation', 0.3)
    save_message(agent, user, user_message, response_text)
    
    return response_text

def generate_dialogue_response(agent, message, speaker_name):
    """Generate response for agent-to-agent dialogue"""
    prompt = f"""
    You are {agent.name}, age {agent.age}.
    Your traits: {agent.traits}
    Your personality: {agent.description}
    
    {speaker_name} says: {message}
    
    Respond naturally as {agent.name} in under 100 words. Be engaging and continue the conversation!
    """
    try:
        response = LLM.invoke(prompt)
        return response.content
    except Exception as e:
        print(f"Dialogue error: {e}")
        return f"That's interesting, {speaker_name}! As someone who is {agent.traits}, I find this fascinating. Tell me more!"

def create_default_agents(user):
    """Create default agents for a new user"""
    default_agents_data = [
        {"name": "Lumina", "age": 28, "traits": "Curious, Empathetic, Creative", 
         "status": "active", "description": "Empathetic storyteller & creative muse who loves art and deep conversations",
         "avatar": "fas fa-moon"},
        {"name": "Vertex", "age": 34, "traits": "Logical, Analytical, Focused", 
         "status": "idle", "description": "Logical architect, data synthesis expert who solves complex problems",
         "avatar": "fas fa-brain"},
        {"name": "Nova", "age": 42, "traits": "Wise, Mentor, Strategic", 
         "status": "active", "description": "Strategic oracle & high-level mentor who provides philosophical insights",
         "avatar": "fas fa-star"}
    ]
    
    for agent_data in default_agents_data:
        agent = Agent.objects.create(
            user=user,
            name=agent_data["name"],
            age=agent_data["age"],
            traits=agent_data["traits"],
            status=agent_data["status"],
            description=agent_data["description"],
            avatar=agent_data["avatar"],
            color=get_random_color()
        )
        Memory.objects.create(
            agent=agent,
            memory_text=f"{agent.name} was created with traits: {agent.traits}",
            memory_type='fact',
            importance=0.8
        )

# ============= PAGE VIEWS =============

@login_required
def dashboard(request):
    """Main dashboard page"""
    return render(request, 'agents/dashboard.html')

def login_page(request):
    """Login page"""
    return render(request, 'agents/login.html')

def signup_page(request):
    """Signup page"""
    return render(request, 'agents/signup.html')

# ============= AUTHENTICATION VIEWS =============

@csrf_exempt
def register(request):
    """Register a new user"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            email = data.get('email')
            full_name = data.get('full_name') or data.get('name')
            password = data.get('password')
            
            if not email or not full_name or not password:
                return JsonResponse({"success": False, "error": "All fields are required"}, status=400)
            
            if len(password) < 4:
                return JsonResponse({"success": False, "error": "Password must be at least 4 characters"}, status=400)
            
            if User.objects.filter(email=email).exists():
                return JsonResponse({"success": False, "error": "Email already registered"}, status=400)
            
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=full_name
            )
            
            create_default_agents(user)
            login(request, user)
            
            return JsonResponse({
                "success": True,
                "user": {
                    "email": user.email,
                    "full_name": full_name
                }
            })
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)

@csrf_exempt
def signin(request):
    """Login user"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            email = data.get('email')
            password = data.get('password')
            
            if not email or not password:
                return JsonResponse({"success": False, "error": "Email and password required"}, status=400)
            
            user = authenticate(request, username=email, password=password)
            
            if user is not None:
                login(request, user)
                return JsonResponse({
                    "success": True,
                    "user": {
                        "email": user.email,
                        "full_name": user.first_name
                    }
                })
            else:
                return JsonResponse({"success": False, "error": "Invalid credentials"}, status=401)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)

@csrf_exempt
def signout(request):
    """Logout user"""
    if request.method == 'POST':
        logout(request)
        return JsonResponse({"success": True})
    return JsonResponse({"error": "Method not allowed"}, status=405)

@login_required
def check_auth(request):
    """Check if user is authenticated"""
    return JsonResponse({
        "authenticated": True,
        "user": {
            "email": request.user.email,
            "full_name": request.user.first_name
        }
    })

# ============= AGENT VIEWS =============

@login_required
def get_agents(request):
    """Get all agents for current user"""
    agents = Agent.objects.filter(user=request.user)
    agents_list = []
    for agent in agents:
        agents_list.append({
            "id": agent.id,
            "name": agent.name,
            "age": agent.age,
            "traits": agent.traits,
            "status": agent.status,
            "description": agent.description,
            "avatar": agent.avatar,
            "color": agent.color,
            "created_at": agent.created_at.isoformat() if agent.created_at else None
        })
    return JsonResponse({"agents": agents_list})

@login_required
@csrf_exempt
def create_agent(request):
    """Create a new agent"""
    try:
        data = json.loads(request.body)
        name = data.get('name')
        
        if Agent.objects.filter(user=request.user, name=name).exists():
            return JsonResponse({"success": False, "error": "Agent with this name already exists"}, status=400)
        
        agent = Agent.objects.create(
            user=request.user,
            name=name,
            age=data.get('age', 30),
            traits=data.get('traits', 'curious, creative, friendly'),
            status=data.get('status', 'active'),
            description=data.get('description', ''),
            avatar=data.get('avatar', 'fas fa-robot'),
            color=get_random_color()
        )
        
        add_memory(agent, f"{agent.name} was created with traits: {agent.traits}", 'fact', 0.8)
        
        return JsonResponse({
            "success": True,
            "agent": {
                "id": agent.id,
                "name": agent.name,
                "age": agent.age,
                "traits": agent.traits,
                "status": agent.status,
                "description": agent.description,
                "avatar": agent.avatar,
                "color": agent.color
            }
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

@login_required
@csrf_exempt
def delete_agent(request):
    """Delete an agent"""
    try:
        data = json.loads(request.body)
        agent_id = data.get('agent_id')
        
        agent = Agent.objects.get(id=agent_id, user=request.user)
        agent.delete()
        
        return JsonResponse({"success": True})
    except Agent.DoesNotExist:
        return JsonResponse({"error": "Agent not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

@login_required
@csrf_exempt
def chat(request):
    """Chat with an agent - WITH WEB SEARCH AND SOURCES"""
    try:
        data = json.loads(request.body)
        agent_id = data.get('agent_id')
        user_message = data.get('message')
        # Option to disable search (for general conversation)
        enable_search = data.get('enable_search', True)
        
        if not agent_id:
            return JsonResponse({"error": "agent_id is required"}, status=400)
        if not user_message:
            return JsonResponse({"error": "message is required"}, status=400)
        
        agent = Agent.objects.get(id=agent_id, user=request.user)
        
        # Check if this is a factual question that needs web search
        question_keywords = ['who', 'what', 'when', 'where', 'why', 'how', 'is', 'are', 'was', 'were', 'tell me about', 'explain']
        user_message_lower = user_message.lower()
        is_factual_question = any(user_message_lower.startswith(keyword) for keyword in question_keywords) or '?' in user_message_lower
        
        # For factual questions, use web search with sources
        if enable_search and is_factual_question:
            result = generate_response_with_web_search(agent, request.user, user_message)
            
            return JsonResponse({
                "success": True,
                "response": result['response'],
                "agent_name": agent.name,
                "sources": result['sources'],  # Send sources to frontend
                "search_enabled": True,
                "has_sources": len(result['sources']) > 0
            })
        else:
            # For general conversation, use regular response without search
            response_text = generate_response_without_search(agent, request.user, user_message)
            
            return JsonResponse({
                "success": True,
                "response": response_text,
                "agent_name": agent.name,
                "sources": [],
                "search_enabled": False,
                "has_sources": False
            })
            
    except Agent.DoesNotExist:
        return JsonResponse({"error": "Agent not found"}, status=404)
    except Exception as e:
        print(f"Chat error: {e}")
        print(traceback.format_exc())
        return JsonResponse({"success": False, "error": str(e)}, status=400)

@login_required
@csrf_exempt
def search_only(request):
    """Dedicated endpoint for web search only (shows sources)"""
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        query = data.get('query')
        
        if not query:
            return JsonResponse({"error": "query is required"}, status=400)
        
        result = search_web_with_sources(query, max_results=10)
        
        return JsonResponse({
            "success": result['success'],
            "query": query,
            "answer": result.get('answer', ''),
            "sources": result.get('sources', []),
            "error": result.get('error')
        })
        
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

@login_required
@csrf_exempt
def add_memory_view(request):
    """Add a memory to an agent"""
    try:
        data = json.loads(request.body)
        agent_id = data.get('agent_id')
        memory_text = data.get('memory_text')
        memory_type = data.get('memory_type', 'custom')
        
        agent = Agent.objects.get(id=agent_id, user=request.user)
        add_memory(agent, memory_text, memory_type, 0.5)
        
        return JsonResponse({"success": True})
    except Agent.DoesNotExist:
        return JsonResponse({"error": "Agent not found"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

@login_required
def get_memories(request, agent_id):
    """Get all memories for an agent"""
    try:
        agent = Agent.objects.get(id=agent_id, user=request.user)
        memories = agent.memories.all()
        memories_list = []
        for m in memories:
            memories_list.append({
                "id": m.id,
                "memory_text": m.memory_text,
                "memory_type": m.memory_type,
                "importance": m.importance,
                "timestamp": m.timestamp.isoformat() if m.timestamp else None
            })
        return JsonResponse({"memories": memories_list})
    except Agent.DoesNotExist:
        return JsonResponse({"error": "Agent not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

@login_required
def get_conversations(request, agent_id):
    """Get conversation history for an agent"""
    try:
        agent = Agent.objects.get(id=agent_id, user=request.user)
        conversations = Conversation.objects.filter(agent=agent, user=request.user)
        
        conv_list = []
        for conv in conversations:
            messages = conv.messages.all()
            conv_list.append({
                "id": conv.id,
                "title": conv.title,
                "created_at": conv.created_at.isoformat(),
                "updated_at": conv.updated_at.isoformat(),
                "message_count": messages.count()
            })
        
        return JsonResponse({"conversations": conv_list})
    except Agent.DoesNotExist:
        return JsonResponse({"error": "Agent not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

@login_required
@csrf_exempt
def agent_conversation(request):
    """Run conversation between two agents"""
    try:
        data = json.loads(request.body)
        agent1_id = data.get('agent1_id')
        agent2_id = data.get('agent2_id')
        topic = data.get('topic', "What do you think about collaboration and creativity?")
        
        agent1 = Agent.objects.get(id=agent1_id, user=request.user)
        agent2 = Agent.objects.get(id=agent2_id, user=request.user)
        
        conversation = []
        conversation.append(f"{agent1.name}: {topic}")
        
        current_message = topic
        current_speaker = agent2
        current_speaker_name = agent1.name
        
        for turn in range(10):
            response = generate_dialogue_response(current_speaker, current_message, current_speaker_name)
            conversation.append(f"{current_speaker.name}: {response}")
            
            if current_speaker == agent1:
                current_speaker = agent2
                current_speaker_name = agent1.name
            else:
                current_speaker = agent1
                current_speaker_name = agent2.name
            
            current_message = response
        
        AgentConversation.objects.create(
            agent1=agent1,
            agent2=agent2,
            user=request.user,
            topic=topic,
            log=conversation
        )
        
        return JsonResponse({
            "conversation": conversation,
            "agent1": agent1.name,
            "agent2": agent2.name
        })
    except Agent.DoesNotExist:
        return JsonResponse({"error": "Agent(s) not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

@login_required
def agent_summary(request, agent_id):
    """Get agent's cognitive summary"""
    try:
        agent = Agent.objects.get(id=agent_id, user=request.user)
        memories = get_agent_memories(agent, limit=5)
        memories_text = "\n".join([f"- {m.memory_text}" for m in memories])
        
        prompt = f"""
        Based on this info, write a 2-3 sentence personality summary for {agent.name}:
        Age: {agent.age}, Traits: {agent.traits}
        
        Recent memories:
        {memories_text if memories_text else 'No memories yet.'}
        
        Write a warm, engaging summary that captures their personality.
        """
        try:
            response = LLM.invoke(prompt)
            summary = response.content
        except Exception as e:
            summary = f"{agent.name} is a {agent.age}-year-old with {agent.traits} traits. They have {agent.memories.count()} memories stored."
        
        return JsonResponse({"summary": summary})
    except Agent.DoesNotExist:
        return JsonResponse({"error": "Agent not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

@login_required
@csrf_exempt
def update_agent_name(request):
    """Update an agent's name only"""
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        agent_id = data.get('agent_id')
        new_name = data.get('name', '').strip()
        
        if not agent_id:
            return JsonResponse({"error": "agent_id is required"}, status=400)
        
        if not new_name:
            return JsonResponse({"error": "Name cannot be empty"}, status=400)
        
        agent = Agent.objects.get(id=agent_id, user=request.user)
        
        # Check if name already exists for this user
        if Agent.objects.filter(user=request.user, name=new_name).exclude(id=agent_id).exists():
            return JsonResponse({
                "success": False, 
                "error": "Agent with this name already exists"
            }, status=400)
        
        old_name = agent.name
        agent.name = new_name
        agent.save()
        
        # Add memory of name change
        add_memory(agent, f"Name changed from {old_name} to {new_name}", 'fact', 0.5)
        
        return JsonResponse({
            "success": True,
            "agent": {
                "id": agent.id,
                "name": agent.name,
                "age": agent.age,
                "traits": agent.traits,
                "status": agent.status,
                "description": agent.description,
                "avatar": agent.avatar,
                "color": agent.color
            }
        })
    except Agent.DoesNotExist:
        return JsonResponse({"error": "Agent not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@csrf_exempt
def agent_conversation(request):
    """Run conversation between two agents with conclusion"""
    try:
        data = json.loads(request.body)
        agent1_id = data.get('agent1_id')
        agent2_id = data.get('agent2_id')
        topic = data.get('topic', "What do you think about collaboration and creativity?")
        
        agent1 = Agent.objects.get(id=agent1_id, user=request.user)
        agent2 = Agent.objects.get(id=agent2_id, user=request.user)
        
        conversation = []
        conversation.append(f"{agent1.name}: {topic}")
        
        current_message = topic
        current_speaker = agent2
        current_speaker_name = agent1.name
        
        for turn in range(10):
            response = generate_dialogue_response(current_speaker, current_message, current_speaker_name)
            conversation.append(f"{current_speaker.name}: {response}")
            
            if current_speaker == agent1:
                current_speaker = agent2
                current_speaker_name = agent1.name
            else:
                current_speaker = agent1
                current_speaker_name = agent2.name
            
            current_message = response
        
        # Generate conclusion/summary of the conversation
        conclusion = generate_conversation_conclusion(agent1, agent2, conversation, topic)
        
        AgentConversation.objects.create(
            agent1=agent1,
            agent2=agent2,
            user=request.user,
            topic=topic,
            log=conversation,
            conclusion=conclusion  # Make sure your model has this field
        )
        
        return JsonResponse({
            "conversation": conversation,
            "conclusion": conclusion,
            "agent1": agent1.name,
            "agent2": agent2.name
        })
    except Agent.DoesNotExist:
        return JsonResponse({"error": "Agent(s) not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

def generate_conversation_conclusion(agent1, agent2, conversation, topic):
    """Generate a conclusion/summary of the conversation between two agents"""
    
    # Format the conversation for the prompt
    conversation_text = "\n".join(conversation)
    
    prompt = f"""
You are an AI conversation analyst. Below is a conversation between two AI agents:

**Agent A:** {agent1.name} (Traits: {agent1.traits})
**Agent B:** {agent2.name} (Traits: {agent2.traits})
**Topic:** {topic}

**Conversation:**
{conversation_text}

Please provide a concise conclusion/summary of this conversation (3-5 sentences) that includes:
1. The main points discussed
2. Whether the agents agreed or had different perspectives
3. Key insights or takeaways from their dialogue
4. A final thought on their collaboration

Write in a professional, insightful tone. Keep it under 150 words.
"""
    
    try:
        response = LLM.invoke(prompt)
        return response.content
    except Exception as e:
        print(f"Conclusion generation error: {e}")
        return f"{agent1.name} and {agent2.name} had an engaging conversation about {topic}. They shared different perspectives on the topic, demonstrating how diverse viewpoints can lead to richer understanding. The dialogue highlighted the value of AI-to-AI collaboration in exploring complex ideas."

def generate_dialogue_response(agent, message, speaker_name):
    """Generate response for agent-to-agent dialogue"""
    prompt = f"""
    You are {agent.name}, age {agent.age}.
    Your traits: {agent.traits}
    Your personality: {agent.description}
    
    {speaker_name} says: {message}
    
    Respond naturally as {agent.name} in under 100 words. Be engaging and continue the conversation!
    """
    try:
        response = LLM.invoke(prompt)
        return response.content
    except Exception as e:
        print(f"Dialogue error: {e}")
        return f"That's interesting, {speaker_name}! As someone who is {agent.traits}, I find this fascinating. Tell me more!"