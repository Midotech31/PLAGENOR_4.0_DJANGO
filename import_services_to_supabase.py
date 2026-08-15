import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

django.setup()


def main():
    from django.core.management import call_command

    print("Seeding services from the version-controlled YAML registry...")
    call_command('seed_services')
    print("\n[SUCCESS] Service registry applied without deleting existing rows.")


if __name__ == '__main__':
    main()
