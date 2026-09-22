from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError

from erp.permissions import TEAM_ROLES,has_access
from erp.services.alerts import send_digest


class Command(BaseCommand):
    help='Create one grouped internal resource notification per active team member per day.'

    def add_arguments(self,parser):
        parser.add_argument('--username')

    def handle(self,*args,**options):
        users=get_user_model().objects.filter(is_active=True,role__in=TEAM_ROLES).order_by('pk')
        if options['username']:
            users=users.filter(username=options['username'])
            if not users.exists():
                raise CommandError('Active team member not found.')
        delivered=0
        for user in users.iterator(chunk_size=100):
            if has_access(user) and send_digest(user) is not None:
                delivered+=1
        self.stdout.write('Daily internal digests recorded or already present: '+str(delivered))
