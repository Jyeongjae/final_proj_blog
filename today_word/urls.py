from django.urls import path
from . import views

urlpatterns=[
    path('search/<str:q>/', views.WordSearch.as_view()),
    path('update_post/<int:pk>/', views.WordUpdate.as_view()),
    path('create_post/', views.WordCreate.as_view()),
    # path('tag/<str:slug>/', views.tag_page),
    # path('category/<str:slug>/', views.category_page),
    path('<int:pk>/', views.WordDetail.as_view()),
    path('', views.WordList.as_view()),

]