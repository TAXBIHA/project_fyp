from django.contrib import admin
from django.urls import path, include

admin.site.site_header = 'AI Agents Admin'
admin.site.site_title = 'AI Agents Admin'
admin.site.index_title = 'AI Agents Admin'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('agents.urls')),  # This makes agents urls available at root
]

# Serve media files during development
# if settings.DEBUG:
#     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)