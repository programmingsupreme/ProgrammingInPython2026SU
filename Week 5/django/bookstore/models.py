from django.db import models


class Author(models.Model):
    name = models.CharField(max_length=255)
    birthdate = models.DateField()
    nationality = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Book(models.Model):
    title = models.CharField(max_length=255)
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    genre = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=5, decimal_places=2)
    publisher = models.CharField(max_length=255)
    isbn = models.CharField(max_length=13)

    def __str__(self):
        return self.title


class Video(models.Model):
    title = models.CharField(max_length=255)
    genre = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=5, decimal_places=2)
    publisher = models.CharField(max_length=255)
    release_date = models.DateField()

    def __str__(self):
        return self.title


class Student(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    birthdate = models.DateField()

    def __str__(self):
        return self.name


class Transaction(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    book = models.ForeignKey(Book, null=True, blank=True, on_delete=models.SET_NULL)
    video = models.ForeignKey(Video, null=True, blank=True, on_delete=models.SET_NULL)
    borrowed_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()

    def __str__(self):
        return f"{self.student.name} borrowed {self.book.title if self.book else self.video.title}"


class Review(models.Model):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    book = models.ForeignKey(Book, null=True, blank=True, on_delete=models.SET_NULL)
    video = models.ForeignKey(Video, null=True, blank=True, on_delete=models.SET_NULL)
    rating = models.IntegerField(choices=RATING_CHOICES)
    comment = models.TextField(blank=True)
    review_date = models.DateField(auto_now_add=True)

    def __str__(self):
        item = self.book.title if self.book else (self.video.title if self.video else "Unknown")
        return f"{self.student.name} rated {item}: {self.rating}/5"


class NewModel(models.Model):
    field1 = models.CharField(max_length=255)
    field2 = models.IntegerField()
    # Add more fields as necessary

    def __str__(self):
        return self.field1
