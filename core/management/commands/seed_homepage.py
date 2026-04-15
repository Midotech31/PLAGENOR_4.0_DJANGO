from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Homepage, HomepageSection, HomepageBlock, Service


class Command(BaseCommand):
    help = 'Seed homepage sections and blocks from current home template content'

    @transaction.atomic
    def handle(self, *args, **options):
        homepage = Homepage.get_active()
        homepage.title = 'Homepage'
        homepage.is_active = True
        homepage.save(update_fields=['title', 'is_active', 'updated_at'])

        self.stdout.write('Seeding homepage sections...')

        section_specs = [
            {
                'slug': 'hero',
                'section_type': 'hero',
                'position': 10,
                'title': 'PLAGENOR 4.0',
                'subtitle': 'Genomics Technology Platform — Higher School of Biological Sciences of Oran · ORAN',
                'description': 'Integrated solution for managing analysis requests, operations tracking and billing within the Higher School of Biological Sciences of Oran.',
                'payload': {
                    'decorative_dna': True,
                },
                'blocks': [
                    {'block_type': 'button', 'position': 10, 'title': 'Soumettre une demande', 'link_url': '', 'payload': {'text': 'Soumettre une demande', 'link': '/accounts/register/', 'style': 'primary'}},
                    {'block_type': 'button', 'position': 20, 'title': 'Soumission invite', 'link_url': '', 'payload': {'text': 'Soumission invité', 'link': '/guest-submit/', 'style': 'secondary'}},
                    {'block_type': 'button', 'position': 30, 'title': 'Voir les services', 'link_url': '', 'payload': {'text': 'Voir les services', 'link': '/services/', 'style': 'secondary'}},
                    {'block_type': 'button', 'position': 40, 'title': 'Suivi de demande', 'link_url': '', 'payload': {'text': 'Suivi de demande', 'link': '/track/', 'style': 'secondary'}},
                ],
            },
            {
                'slug': 'partners',
                'section_type': 'partners',
                'position': 20,
                'title': 'INSTITUTIONS & PARTENAIRES',
                'subtitle': '',
                'description': '',
                'payload': {},
                'blocks': [
                    {'block_type': 'logo', 'position': 10, 'title': 'ESSBO', 'link_url': 'http://www.essb-oran.edu.dz/', 'payload': {'name': 'ESSBO', 'link': 'http://www.essb-oran.edu.dz/', 'image_alt': 'ESSBO'}, 'image_alt': 'ESSBO'},
                    {'block_type': 'logo', 'position': 20, 'title': 'IBTIKAR-DGRSDT', 'link_url': 'https://ibtikar.dgrsdt.dz/', 'payload': {'name': 'IBTIKAR-DGRSDT', 'link': 'https://ibtikar.dgrsdt.dz/', 'image_alt': 'IBTIKAR-DGRSDT'}, 'image_alt': 'IBTIKAR-DGRSDT'},
                    {'block_type': 'logo', 'position': 30, 'title': 'GENOCLAB', 'link_url': 'https://genoclab.my.canva.site/genoclab-essbo', 'payload': {'name': 'GENOCLAB', 'link': 'https://genoclab.my.canva.site/genoclab-essbo', 'image_alt': 'GENOCLAB'}, 'image_alt': 'GENOCLAB'},
                    {'block_type': 'logo', 'position': 40, 'title': 'DGRSDT', 'link_url': 'https://www.dgrsdt.dz/', 'payload': {'name': 'DGRSDT', 'link': 'https://www.dgrsdt.dz/', 'image_alt': 'DGRSDT'}, 'image_alt': 'DGRSDT'},
                    {'block_type': 'logo', 'position': 50, 'title': 'PLAGENOR', 'link_url': '', 'payload': {'name': 'PLAGENOR', 'link': '', 'image_alt': 'PLAGENOR'}, 'image_alt': 'PLAGENOR'},
                ],
            },
            {
                'slug': 'services',
                'section_type': 'services',
                'position': 30,
                'title': 'Nos Services',
                'subtitle': 'Scientific and technical analyses offered by the Higher School of Biological Sciences of Oran laboratory',
                'description': '',
                'payload': {},
                'blocks': [],
            },
            {
                'slug': 'stats',
                'section_type': 'stats',
                'position': 40,
                'title': 'Indicateurs clés',
                'subtitle': '',
                'description': '',
                'payload': {},
                'blocks': [
                    {'block_type': 'stat', 'position': 10, 'title': 'Analyses disponibles', 'payload': {'value': str(Service.objects.filter(active=True).count()), 'label': 'Analyses disponibles'}},
                    {'block_type': 'stat', 'position': 20, 'title': 'Canaux', 'payload': {'value': '2', 'label': 'Canaux (IBTIKAR/GENOCLAB)'}},
                    {'block_type': 'stat', 'position': 30, 'title': 'Partenaires', 'payload': {'value': '5', 'label': 'Institutions partenaires'}},
                ],
            },
            {
                'slug': 'about',
                'section_type': 'about',
                'position': 50,
                'title': 'Organisation',
                'subtitle': 'HSBSO → PLAGENOR → GENOCLAB',
                'description': 'The Higher School of Biological Sciences of Oran (HSBSO) hosts the PLAGENOR platform, which manages two service channels: IBTIKAR for the internal academic community, and GENOCLAB for external services.',
                'payload': {},
                'blocks': [],
            },
            {
                'slug': 'contact',
                'section_type': 'contact',
                'position': 60,
                'title': 'Contact',
                'subtitle': 'Higher School of Biological Sciences of Oran',
                'description': '',
                'payload': {},
                'blocks': [
                    {'block_type': 'text', 'position': 10, 'title': 'Institution', 'payload': {'content': 'ESSBO — Université d\'Oran'}},
                    {'block_type': 'text', 'position': 20, 'title': 'Email', 'payload': {'content': 'contact@plagenor.essbo.dz'}},
                ],
            },
        ]

        services_section = next(item for item in section_specs if item['slug'] == 'services')
        service_blocks = []
        for idx, service in enumerate(Service.objects.filter(active=True).order_by('code')[:8], start=1):
            service_blocks.append({
                'block_type': 'card',
                'position': idx * 10,
                'title': service.name,
                'text': (service.description or '')[:400],
                'link_url': '',
                'image': service.image,
                'image_alt': service.name,
                'payload': {
                    'title': service.name,
                    'text': (service.description or '')[:400],
                    'link': f'/services/{service.code}/',
                    'image_alt': service.name,
                },
            })
        services_section['blocks'] = service_blocks

        for spec in section_specs:
            section, created = HomepageSection.objects.update_or_create(
                homepage=homepage,
                slug=spec['slug'],
                defaults={
                    'section_type': spec['section_type'],
                    'title': spec['title'],
                    'subtitle': spec['subtitle'],
                    'description': spec['description'],
                    'position': spec['position'],
                    'is_active': True,
                    'payload': spec['payload'],
                },
            )
            section.blocks.all().delete()
            for block_data in spec['blocks']:
                image_value = block_data.pop('image', None)
                block = HomepageBlock.objects.create(section=section, is_active=True, **block_data)
                if image_value:
                    block.image = image_value
                    block.save(update_fields=['image'])

            status = 'created' if created else 'updated'
            self.stdout.write(f" - [{status}] section '{section.slug}'")

        self.stdout.write(self.style.SUCCESS('Homepage seed complete.'))
