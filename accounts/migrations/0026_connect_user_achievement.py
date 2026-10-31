from django.db import migrations, models


def get_pairs(model, db):
    """All (user_id, achievement_id) tuples from the join table, represented as a set"""
    return set(model.objects.using(db).values_list("user_id", "achievement_id"))


def copy_old_m2m_to_user_achievement(apps, schema_editor):
    db = schema_editor.connection.alias
    User = apps.get_model("accounts", "User")
    UserAchievement = apps.get_model("accounts", "UserAchievement")
    OldThrough = User._meta.get_field("achievement").remote_field.through

    missing = get_pairs(OldThrough, db) - get_pairs(UserAchievement, db)

    UserAchievement.objects.using(db).bulk_create(
        [
            UserAchievement(
                user_id=user_id,
                achievement_id=achievement_id,
                earned_at=None,
                source_review=None,
            )
            for user_id, achievement_id in missing
        ]
    )


def copy_user_achievement_to_old_m2m(apps, schema_editor):
    db = schema_editor.connection.alias
    User = apps.get_model("accounts", "User")
    UserAchievement = apps.get_model("accounts", "UserAchievement")
    OldThrough = User._meta.get_field("achievement").remote_field.through

    missing = get_pairs(UserAchievement, db) - get_pairs(OldThrough, db)

    OldThrough.objects.using(db).bulk_create(
        [
            OldThrough(user_id=user_id, achievement_id=achievement_id)
            for user_id, achievement_id in missing
        ]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0025_rename_avatar_image_achievement_badge_image"),
    ]

    operations = [
        migrations.RunPython(
            code=copy_old_m2m_to_user_achievement,
            reverse_code=copy_user_achievement_to_old_m2m,
        ),
        migrations.RemoveField(
            model_name="user",
            name="achievement",
        ),
        migrations.AddField(
            model_name="user",
            name="achievement",
            field=models.ManyToManyField(
                blank=True,
                related_name="users",
                through="accounts.UserAchievement",
                to="accounts.achievement",
                verbose_name="Achievements",
            ),
        ),
    ]