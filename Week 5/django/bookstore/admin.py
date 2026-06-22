from django.contrib import admin
from .models import NewModel, Author, Book, Video, Review, Student

admin.site.register(NewModel)
admin.site.register(Author)
admin.site.register(Book)
admin.site.register(Video)
admin.site.register(Review)
admin.site.register(Student)
