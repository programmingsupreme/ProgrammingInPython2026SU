from django.shortcuts import render
from .models import NewModel, Book, Author, Video, Review

def new_model_list(request):
	items = NewModel.objects.all()
	return render(request, 'new_model_list.html', {'items': items})

def index(request):
	books = Book.objects.all()
	authors = Author.objects.all()
	videos = Video.objects.all()
	return render(request, 'bookstore/index.html', {'books' : books, 'authors' : authors, 'videos' : videos})

def review_list(request):
	reviews = Review.objects.select_related('student', 'book', 'video').all()
	return render(request, 'bookstore/reviews.html', {'reviews': reviews})
