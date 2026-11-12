from django.core.management.base import BaseCommand

from gestion_rooms.services import notify_due_cleaning


class Command(BaseCommand):
    help = "Envoie les notifications de nettoyage arrivées à échéance (à lancer chaque minute via cron / planificateur)."

    def handle(self, *args, **options):
        self.stdout.write(f'{notify_due_cleaning()} rappel(s) envoyé(s).')
