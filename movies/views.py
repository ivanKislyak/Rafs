from django.shortcuts import render

list_of_movies = [
    {
        'id': 1,
        'name': 'Clean, Shaven',
        'year': 1993,
        'rate': 7.4,
        'description': "It follows Peter Winter, a schizophrenic man recently released from a mental institution, as he navigates terrifying sensory hallucinations and desperately tries to reclaim his daughter from her adoptive family",
        'path': 'clean_shaven.jpg'
    },

    {
        'id': 2,
        'name': 'Fight Club',
        'year': 1999,
        'rate': 10.0,
        'description': "It follows a disillusioned, insomniac office worker who—along with a charismatic soap salesman—founds an underground fight club that spirals into an anti-consumerist, anarchic terrorist organization",
        'path': None
    },

    {
        'id': 3,
        'name': 'Pi',
        'year': 1998,
        'rate': None,
        'description': "It follows Max Cohen, a paranoid mathematician who believes everything in nature can be understood through numbers. His obsession with finding a universal pattern leads him to build a supercomputer that uncovers a 216-digit number",
        'path': 'pi.jpg'
    },
]

def catalog(request):
    return render(request, "movies/catalog.html", context={"movies": list_of_movies})

