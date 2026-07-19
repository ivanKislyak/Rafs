from django.db import models

class Movie(models.Model):
    name = models.CharField(max_length=200) # Night of the Day of the Dawn of the Son of the Bride...
    year = models.PositiveSmallIntegerField()
    rate = models.DecimalField(decimal_places=1, max_digits=3, null=True, blank=True)
    description = models.TextField(blank=True)
    path = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-rate', 'name']

    def __str__(self):
        if self.year:
            return f"{self.name}, ({self.year})"
        else:
            return self.name
