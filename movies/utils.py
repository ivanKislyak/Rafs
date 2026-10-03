from django.core.mail import send_mail
from django.conf import settings

def send_confirm_moderation_email(user_email: str):
    send_mail(
        "Congratulations! You have been accepted as a moderator",
        "You can now add the content you need yourself using https://rafs.app/movies/wikidata/search/\n" \
        "If you encounter an error, please contact the administrator",
        ""
    )