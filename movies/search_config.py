TITLE_FIELDS = {
    'movie': ('wikidata_name', 'name'),
    'person': ('name',),
    'studio': ('name',),
    'user': ('username',),
    'country': ('name',),
    'genre': ('name',),
    'typeofwork': ('name',)
}

DESCRIPTION_FIELDS = {
    'movie': ('wikidata_description', 'description',),
    'review': ('text',), 
    'person': ('bio',),
    'user': ('about',),
}

IMAGE_FIELDS = {
    'movie': ('cover_url', 'cover'),
    'person': ('photo_url', 'photo'),
    'studio': ('logo_url', 'logo'),
    'user': ('avatar_image',),
    'country': ('banner_url', 'banner'), 
    'genre': ('banner_url', 'banner'),
    'typeofwork': ('banner_url', 'banner'),
}