from django.db import models


class TypeOfWork(models.Model):
    wikidata_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)

    def str(self):
        return self.name


class Genre(models.Model):
    wikidata_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)

    def str(self):
        return self.name


class Country(models.Model):
    wikidata_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)

    def str(self):
        return self.name


class Studio(models.Model):
    wikidata_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100) 

    def str(self):
        return self.name


class Person(models.Model):
    wikidata_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)

    def str(self):
        return self.name





