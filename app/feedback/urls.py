from django.urls import path
from . import views

urlpatterns = [
    path('react/<int:entry_page_id>/', views.react, name='feedback_react'),
    path('comment/<int:entry_page_id>/', views.add_comment, name='feedback_add_comment'),
    path('comment/<int:comment_id>/delete/', views.delete_comment, name='feedback_delete_comment'),
]
