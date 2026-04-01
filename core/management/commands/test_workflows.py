"""
PLAGENOR 4.0 - Comprehensive Workflow Test Command

This command tests the complete IBTIKAR and GENOCLAB workflows end-to-end,
verifying state transitions, PDF generation, notifications, and budget tracking.

Usage:
    python manage.py test_workflows [--cleanup] [--verbose]

Options:
    --cleanup   Remove test data after testing
    --verbose   Show detailed output
"""
import sys
import os
from datetime import datetime, timedelta
from io import BytesIO
from typing import List, Dict, Tuple, Optional
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.conf import settings


class bcolors:
    """Terminal colors for output formatting."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Command(BaseCommand):
    help = 'Comprehensive workflow testing for IBTIKAR and GENOCLAB pipelines'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Remove test data after testing',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_results: List[Dict] = []
        self.verbose = False
        self.test_users = {}
        self.test_requests = {}

    def log(self, message: str, level: str = 'info'):
        """Log message with color coding."""
        color_map = {
            'info': bcolors.OKBLUE,
            'success': bcolors.OKGREEN,
            'warning': bcolors.WARNING,
            'error': bcolors.FAIL,
            'header': bcolors.HEADER,
            'bold': bcolors.BOLD,
        }
        color = color_map.get(level, bcolors.ENDC)
        self.stdout.write(f"{color}{message}{bcolors.ENDC}")

    def record_test(self, category: str, test_name: str, passed: bool, details: str = '',
                   expected: str = '', actual: str = ''):
        """Record a test result."""
        result = {
            'category': category,
            'test': test_name,
            'passed': passed,
            'details': details,
            'expected': expected,
            'actual': actual,
            'timestamp': timezone.now().isoformat(),
        }
        self.test_results.append(result)

        status = 'PASS' if passed else 'FAIL'
        level = 'success' if passed else 'error'
        self.log(f"  [{status}] {test_name}", level)
        if self.verbose and details:
            self.log(f"       {details}", 'info')
        if not passed and expected and actual:
            self.log(f"       Expected: {expected}", 'info')
            self.log(f"       Actual: {actual}", 'info')

    def print_header(self, text: str):
        """Print a formatted header."""
        self.log("\n" + "=" * 70, 'header')
        self.log(f"  {text}", 'bold')
        self.log("=" * 70, 'header')

    def print_section(self, text: str):
        """Print a section header."""
        self.log(f"\n  {text}", 'bold')
        self.log("  " + "-" * 50, 'info')

    def handle(self, *args, **options):
        """Main entry point for the command."""
        self.verbose = options['verbose']
        cleanup = options['cleanup']

        self.print_header("PLAGENOR 4.0 - WORKFLOW TEST SUITE")
        self.log(f"Started at: {timezone.now().isoformat()}")
        self.log(f"Cleanup after test: {cleanup}")
        self.log("")

        try:
            with transaction.atomic():
                # Step 1: Create Test Users
                self.create_test_users()

                # Step 2: Ensure test service exists
                self.ensure_test_service()

                # Step 3: Test IBTIKAR Pipeline
                self.test_ibtikar_pipeline()

                # Step 4: Test GENOCLAB Pipeline
                self.test_genoclab_pipeline()

                # Step 5: Generate Summary
                self.print_summary()

                if cleanup:
                    self.log("\n[Cleanup] Removing test data...")
                    self.cleanup_test_data()
                    self.log("[Cleanup] Complete.")

        except Exception as e:
            self.log(f"\nCRITICAL ERROR: {str(e)}", 'error')
            if self.verbose:
                import traceback
                self.log(traceback.format_exc(), 'error')
            sys.exit(1)

    def create_test_users(self):
        """Create test users for each role."""
        self.print_section("CREATING TEST USERS")

        from accounts.models import User, MemberProfile

        user_configs = [
            {
                'key': 'requester',
                'username': 'test_ibtikar_requester',
                'email': 'test.requester@plagenor.dz',
                'first_name': 'Test',
                'last_name': 'Requester',
                'role': 'REQUESTER',
                ' organization': 'Université de Test',
                'laboratory': 'Labo Test',
                'phone': '+213550000001',
                'ibtikar_id': 'IBK-TEST-001',
            },
            {
                'key': 'client',
                'username': 'test_genoclab_client',
                'email': 'test.client@plagenor.dz',
                'first_name': 'Test',
                'last_name': 'Client',
                'role': 'CLIENT',
                'organization': 'Entreprise Test',
                'phone': '+213550000002',
            },
            {
                'key': 'member',
                'username': 'test_analyst',
                'email': 'test.analyst@plagenor.dz',
                'first_name': 'Test',
                'last_name': 'Analyst',
                'role': 'MEMBER',
                'phone': '+213550000003',
            },
            {
                'key': 'admin_ops',
                'username': 'test_admin_ops',
                'email': 'test.admin@plagenor.dz',
                'first_name': 'Test',
                'last_name': 'Admin',
                'role': 'PLATFORM_ADMIN',
                'phone': '+213550000004',
            },
            {
                'key': 'superadmin',
                'username': 'test_superadmin',
                'email': 'test.superadmin@plagenor.dz',
                'first_name': 'Test',
                'last_name': 'SuperAdmin',
                'role': 'SUPER_ADMIN',
                'is_staff': True,
                'is_superuser': True,
                'phone': '+213550000005',
            },
        ]

        for config in user_configs:
            key = config.pop('key')
            try:
                user, created = User.objects.get_or_create(
                    username=config['username'],
                    defaults=config
                )
                if created:
                    user.set_password('TestPass123!')
                    user.save()
                    if user.role == 'MEMBER':
                        MemberProfile.objects.get_or_create(
                            user=user,
                            defaults={'max_load': 5, 'available': True}
                        )
                    self.record_test('Users', f'Create {key} ({user.role})', True,
                                   f"User ID: {user.id}")
                else:
                    self.record_test('Users', f'Get existing {key}', True,
                                   f"User ID: {user.id}")
                self.test_users[key] = user
            except Exception as e:
                self.record_test('Users', f'Create {key}', False, str(e))
                raise

    def ensure_test_service(self):
        """Ensure a test service exists for workflow testing."""
        self.print_section("ENSURING TEST SERVICE")

        from core.models import Service

        try:
            service, created = Service.objects.get_or_create(
                code='TEST-EGTP-Seq02',
                defaults={
                    'name': 'Test DNA Sequencing Service',
                    'description': 'Test service for workflow validation',
                    'channel_availability': 'BOTH',
                    'service_type': 'Analysis',
                    'ibtikar_price': 15000.00,
                    'genoclab_price': 20000.00,
                    'turnaround_days': 7,
                    'service_code': 'TEST-EGTP-Seq02',
                    'form_version': 'V 01',
                    'ibtikar_instructions': 'Test instructions for IBTIKAR form',
                    'checklist_items': ['Verify sample quality', 'Check documentation'],
                    'deliverables': 'Report PDF, Raw data files',
                    'processing_steps': 'Sample reception, DNA extraction, Sequencing, Analysis',
                    'analysis_workflow': 'Quality control, Assembly, Annotation',
                    'active': True,
                }
            )
            self.record_test('Service', 'Create/Update test service', True,
                           f"Service ID: {service.id}, Code: {service.code}")
            self.test_service = service
        except Exception as e:
            self.record_test('Service', 'Create test service', False, str(e))
            raise

    def test_ibtikar_pipeline(self):
        """Test the complete IBTIKAR workflow pipeline."""
        self.print_section("TESTING IBTIKAR PIPELINE")

        from core.models import Request, RequestHistory
        from core.services.ibtikar import submit_ibtikar_request
        from core.workflow import transition
        from core.state_machine import validate_transition

        requester = self.test_users['requester']
        admin_ops = self.test_users['admin_ops']
        member = self.test_users['member']

        # Step 1: Create IBTIKAR Request
        self.log("\n  [Step 1] Creating IBTIKAR request...")
        try:
            request_data = {
                'title': 'Test IBTIKAR Analysis Request',
                'description': 'This is a test request for workflow validation',
                'service_id': str(self.test_service.id),
                'urgency': 'Normal',
                'budget_amount': 15000.00,
                'declared_ibtikar_balance': 200000.00,
                'service_params': {'sample_type': 'DNA', 'quantity': 5},
                'sample_table': [
                    {'id': 1, 'code': 'S001', 'type': 'Blood', 'volume': '2ml'},
                    {'id': 2, 'code': 'S002', 'type': 'Blood', 'volume': '2ml'},
                ],
                'requester_data': {
                    'university': 'Test University',
                    'program': 'PhD Biology',
                },
            }
            ibtikar_request = submit_ibtikar_request(request_data, requester)
            self.test_requests['ibtikar'] = ibtikar_request
            self.record_test('IBTIKAR', 'Create request', True,
                           f"Request ID: {ibtikar_request.display_id}")
        except Exception as e:
            self.record_test('IBTIKAR', 'Create request', False, str(e))
            return

        # Verify initial state
        self.assert_state(ibtikar_request, 'SUBMITTED', 'IBTIKAR')

        # Step 2: Admin validates pedagogically
        self.log("\n  [Step 2] Admin validates pedagogically...")
        try:
            transition(ibtikar_request, 'VALIDATION_PEDAGOGIQUE', admin_ops,
                      notes='Pedagogical validation passed')
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Admin pedagogical validation', True,
                           f"Status: {ibtikar_request.status}")
        except Exception as e:
            self.record_test('IBTIKAR', 'Admin pedagogical validation', False, str(e))
            return

        self.assert_state(ibtikar_request, 'VALIDATION_PEDAGOGIQUE', 'IBTIKAR')

        # Step 3: Admin validates financially
        self.log("\n  [Step 3] Admin validates financially...")
        try:
            ibtikar_request.admin_validated_price = 15000.00
            ibtikar_request.save()
            transition(ibtikar_request, 'VALIDATION_FINANCE', admin_ops,
                      notes='Financial validation passed')
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Admin financial validation', True,
                           f"Status: {ibtikar_request.status}")
        except Exception as e:
            self.record_test('IBTIKAR', 'Admin financial validation', False, str(e))
            return

        self.assert_state(ibtikar_request, 'VALIDATION_FINANCE', 'IBTIKAR')

        # Step 4: Platform Note Generation
        self.log("\n  [Step 4] Generating platform note...")
        try:
            transition(ibtikar_request, 'PLATFORM_NOTE_GENERATED', admin_ops)
            ibtikar_request.refresh_from_db()

            # Check if PDF was generated
            has_platform_note = bool(ibtikar_request.generated_platform_note)
            self.record_test('IBTIKAR', 'Platform Note PDF generated', has_platform_note,
                           f"PDF exists: {has_platform_note}")
        except Exception as e:
            self.record_test('IBTIKAR', 'Platform Note generation', False, str(e))
            return

        self.assert_state(ibtikar_request, 'PLATFORM_NOTE_GENERATED', 'IBTIKAR')

        # Step 5: IBTIKAR submission pending and code submitted
        self.log("\n  [Step 5] IBTIKAR code submission...")
        try:
            transition(ibtikar_request, 'IBTIKAR_SUBMISSION_PENDING', admin_ops)
            ibtikar_request.refresh_from_db()

            # Simulate IBTIKAR code submission by requester
            ibtikar_request.ibtikar_external_code = 'EXT-IBK-2024-001'
            ibtikar_request.save()

            transition(ibtikar_request, 'IBTIKAR_CODE_SUBMITTED', requester)
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'IBTIKAR code submission', True,
                           f"External code: {ibtikar_request.ibtikar_external_code}")
        except Exception as e:
            self.record_test('IBTIKAR', 'IBTIKAR code submission', False, str(e))
            return

        self.assert_state(ibtikar_request, 'IBTIKAR_CODE_SUBMITTED', 'IBTIKAR')

        # Step 6: Assign to member
        self.log("\n  [Step 6] Assigning to member...")
        try:
            from accounts.models import MemberProfile

            member_profile = MemberProfile.objects.get(user=member)
            ibtikar_request.assigned_to = member_profile
            ibtikar_request.save()

            transition(ibtikar_request, 'ASSIGNED', admin_ops)
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Assign to member', True,
                           f"Assigned to: {member_profile.user.username}")
        except Exception as e:
            self.record_test('IBTIKAR', 'Assign to member', False, str(e))
            return

        self.assert_state(ibtikar_request, 'ASSIGNED', 'IBTIKAR')

        # Step 7: Member accepts assignment
        self.log("\n  [Step 7] Member accepts assignment...")
        try:
            transition(ibtikar_request, 'PENDING_ACCEPTANCE', admin_ops)
            ibtikar_request.refresh_from_db()

            # Accept assignment
            ibtikar_request.assignment_accepted = True
            ibtikar_request.assignment_accepted_at = timezone.now()
            ibtikar_request.save()

            transition(ibtikar_request, 'ACCEPTED', member)
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Member accepts assignment', True)
        except Exception as e:
            self.record_test('IBTIKAR', 'Member accepts assignment', False, str(e))
            return

        self.assert_state(ibtikar_request, 'ACCEPTED', 'IBTIKAR')

        # Step 8: Member proposes appointment
        self.log("\n  [Step 8] Member proposes appointment...")
        try:
            ibtikar_request.appointment_date = timezone.now().date() + timedelta(days=7)
            ibtikar_request.appointment_proposed_by = member
            ibtikar_request.save()

            transition(ibtikar_request, 'APPOINTMENT_PROPOSED', member)
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Member proposes appointment', True,
                           f"Proposed date: {ibtikar_request.appointment_date}")
        except Exception as e:
            self.record_test('IBTIKAR', 'Member proposes appointment', False, str(e))
            return

        self.assert_state(ibtikar_request, 'APPOINTMENT_PROPOSED', 'IBTIKAR')

        # Step 9: Requester confirms appointment
        self.log("\n  [Step 9] Requester confirms appointment...")
        try:
            ibtikar_request.appointment_confirmed = True
            ibtikar_request.appointment_confirmed_at = timezone.now()
            ibtikar_request.save()

            transition(ibtikar_request, 'APPOINTMENT_CONFIRMED', requester)
            ibtikar_request.refresh_from_db()

            # Check if Reception Form PDF was generated
            has_reception_form = bool(ibtikar_request.generated_reception_form)
            self.record_test('IBTIKAR', 'Requester confirms appointment', True)
            self.record_test('IBTIKAR', 'Reception Form PDF generated', has_reception_form)
        except Exception as e:
            self.record_test('IBTIKAR', 'Requester confirms appointment', False, str(e))
            return

        self.assert_state(ibtikar_request, 'APPOINTMENT_CONFIRMED', 'IBTIKAR')

        # Step 10: Sample received and analysis workflow
        self.log("\n  [Step 10] Sample reception and analysis...")
        try:
            # Sample received
            transition(ibtikar_request, 'SAMPLE_RECEIVED', member)
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Sample received', True)

            # Analysis started
            transition(ibtikar_request, 'ANALYSIS_STARTED', member)
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Analysis started', True)

            # Analysis finished
            transition(ibtikar_request, 'ANALYSIS_FINISHED', member)
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Analysis finished', True)
        except Exception as e:
            self.record_test('IBTIKAR', 'Analysis workflow', False, str(e))
            return

        self.assert_state(ibtikar_request, 'ANALYSIS_FINISHED', 'IBTIKAR')

        # Step 11: Report uploaded
        self.log("\n  [Step 11] Member uploads report...")
        try:
            # Create a dummy PDF file for the report
            dummy_pdf = BytesIO(b"%PDF-1.4 dummy report content")
            from django.core.files.base import ContentFile
            ibtikar_request.report_file.save(
                f"report_{ibtikar_request.display_id}.pdf",
                ContentFile(dummy_pdf.read()),
                save=True
            )

            transition(ibtikar_request, 'REPORT_UPLOADED', member)
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Report uploaded', True,
                           f"Report file: {ibtikar_request.report_file.name}")
        except Exception as e:
            self.record_test('IBTIKAR', 'Report uploaded', False, str(e))
            return

        self.assert_state(ibtikar_request, 'REPORT_UPLOADED', 'IBTIKAR')

        # Step 12: Admin validates report
        self.log("\n  [Step 12] Admin validates report...")
        try:
            transition(ibtikar_request, 'REPORT_VALIDATED', admin_ops)
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Admin validates report', True)
        except Exception as e:
            self.record_test('IBTIKAR', 'Admin validates report', False, str(e))
            return

        self.assert_state(ibtikar_request, 'REPORT_VALIDATED', 'IBTIKAR')

        # Step 13: Report sent to requester
        self.log("\n  [Step 13] Sending report to requester...")
        try:
            transition(ibtikar_request, 'SENT_TO_REQUESTER', admin_ops)
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Report sent to requester', True)
        except Exception as e:
            self.record_test('IBTIKAR', 'Report sent to requester', False, str(e))
            return

        self.assert_state(ibtikar_request, 'SENT_TO_REQUESTER', 'IBTIKAR')

        # Step 14: Requester confirms receipt and rates
        self.log("\n  [Step 14] Requester confirms receipt and rates...")
        try:
            ibtikar_request.receipt_confirmed = True
            ibtikar_request.receipt_confirmed_at = timezone.now()
            ibtikar_request.service_rating = 5
            ibtikar_request.rating_comment = 'Excellent service!'
            ibtikar_request.rated_at = timezone.now()
            ibtikar_request.save()

            transition(ibtikar_request, 'COMPLETED', requester)
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Requester confirms receipt', True)
            self.record_test('IBTIKAR', 'Requester rating submitted', True,
                           f"Rating: {ibtikar_request.service_rating}/5")
        except Exception as e:
            self.record_test('IBTIKAR', 'Receipt confirmation', False, str(e))
            return

        self.assert_state(ibtikar_request, 'COMPLETED', 'IBTIKAR')

        # Step 15: Close request
        self.log("\n  [Step 15] Closing request...")
        try:
            transition(ibtikar_request, 'CLOSED', admin_ops)
            ibtikar_request.refresh_from_db()
            self.record_test('IBTIKAR', 'Request closed', True)
        except Exception as e:
            self.record_test('IBTIKAR', 'Request closed', False, str(e))
            return

        self.assert_state(ibtikar_request, 'CLOSED', 'IBTIKAR')

        # Step 16: Verify notifications
        self.log("\n  [Step 16] Verifying notifications...")
        self.verify_notifications(ibtikar_request, 'IBTIKAR')

        # Step 17: Verify budget tracking
        self.log("\n  [Step 17] Verifying budget tracking...")
        self.verify_budget_tracking(ibtikar_request, requester)

        # Step 18: Verify PDFs generated
        self.log("\n  [Step 18] Verifying PDF generation...")
        self.verify_pdfs(ibtikar_request, 'IBTIKAR')

        self.log("\n  IBTIKAR Pipeline Complete!")

    def test_genoclab_pipeline(self):
        """Test the complete GENOCLAB workflow pipeline."""
        self.print_section("TESTING GENOCLAB PIPELINE")

        from core.models import Request, RequestHistory
        from core.services.genoclab import submit_genoclab_request
        from core.workflow import transition
        from core.state_machine import validate_transition

        client = self.test_users['client']
        admin_ops = self.test_users['admin_ops']
        member = self.test_users['member']

        # Step 1: Create GENOCLAB Request
        self.log("\n  [Step 1] Creating GENOCLAB request...")
        try:
            request_data = {
                'title': 'Test GENOCLAB Analysis Request',
                'description': 'This is a test request for GENOCLAB workflow validation',
                'service_id': str(self.test_service.id),
                'urgency': 'Normal',
                'service_params': {'sample_type': 'DNA', 'quantity': 3},
                'sample_table': [
                    {'id': 1, 'code': 'C001', 'type': 'Tissue', 'volume': '1g'},
                    {'id': 2, 'code': 'C002', 'type': 'Tissue', 'volume': '1g'},
                ],
            }
            genoclab_request = submit_genoclab_request(request_data, client)
            self.test_requests['genoclab'] = genoclab_request
            self.record_test('GENOCLAB', 'Create request', True,
                           f"Request ID: {genoclab_request.display_id}")
        except Exception as e:
            self.record_test('GENOCLAB', 'Create request', False, str(e))
            return

        self.assert_state(genoclab_request, 'REQUEST_CREATED', 'GENOCLAB')

        # Step 2: Admin creates quote
        self.log("\n  [Step 2] Admin creates quote...")
        try:
            transition(genoclab_request, 'QUOTE_DRAFT', admin_ops)
            genoclab_request.refresh_from_db()

            # Set quote details
            genoclab_request.quote_amount = 25000.00
            genoclab_request.quote_detail = {
                'Service': 20000.00,
                'Processing': 5000.00,
            }
            genoclab_request.save()

            transition(genoclab_request, 'QUOTE_SENT', admin_ops)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Admin creates and sends quote', True,
                           f"Quote amount: {genoclab_request.quote_amount} DZD")
        except Exception as e:
            self.record_test('GENOCLAB', 'Admin creates quote', False, str(e))
            return

        self.assert_state(genoclab_request, 'QUOTE_SENT', 'GENOCLAB')

        # Step 3: Client validates quote
        self.log("\n  [Step 3] Client validates quote...")
        try:
            transition(genoclab_request, 'QUOTE_VALIDATED_BY_CLIENT', client)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Client validates quote', True)
        except Exception as e:
            self.record_test('GENOCLAB', 'Client validates quote', False, str(e))
            return

        self.assert_state(genoclab_request, 'QUOTE_VALIDATED_BY_CLIENT', 'GENOCLAB')

        # Step 4: Client uploads order (purchase order)
        self.log("\n  [Step 4] Client uploads purchase order...")
        try:
            # Create a dummy order file
            dummy_order = BytesIO(b"Dummy purchase order content")
            from django.core.files.base import ContentFile
            genoclab_request.order_file.save(
                f"order_{genoclab_request.display_id}.pdf",
                ContentFile(dummy_order.read()),
                save=True
            )
            genoclab_request.order_uploaded_at = timezone.now()
            genoclab_request.save()

            transition(genoclab_request, 'ORDER_UPLOADED', client)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Client uploads purchase order', True,
                           f"Order file: {genoclab_request.order_file.name}")
        except Exception as e:
            self.record_test('GENOCLAB', 'Client uploads order', False, str(e))
            return

        self.assert_state(genoclab_request, 'ORDER_UPLOADED', 'GENOCLAB')

        # Step 5: Assign to member
        self.log("\n  [Step 5] Assigning to member...")
        try:
            from accounts.models import MemberProfile

            member_profile = MemberProfile.objects.get(user=member)
            genoclab_request.assigned_to = member_profile
            genoclab_request.save()

            transition(genoclab_request, 'ASSIGNED', admin_ops)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Assign to member', True)
        except Exception as e:
            self.record_test('GENOCLAB', 'Assign to member', False, str(e))
            return

        self.assert_state(genoclab_request, 'ASSIGNED', 'GENOCLAB')

        # Step 6: Member accepts
        self.log("\n  [Step 6] Member accepts assignment...")
        try:
            transition(genoclab_request, 'PENDING_ACCEPTANCE', admin_ops)
            genoclab_request.refresh_from_db()

            genoclab_request.assignment_accepted = True
            genoclab_request.assignment_accepted_at = timezone.now()
            genoclab_request.save()

            transition(genoclab_request, 'ACCEPTED', member)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Member accepts assignment', True)
        except Exception as e:
            self.record_test('GENOCLAB', 'Member accepts assignment', False, str(e))
            return

        self.assert_state(genoclab_request, 'ACCEPTED', 'GENOCLAB')

        # Step 7: Member proposes appointment
        self.log("\n  [Step 7] Member proposes appointment...")
        try:
            genoclab_request.appointment_date = timezone.now().date() + timedelta(days=3)
            genoclab_request.appointment_proposed_by = member
            genoclab_request.save()

            transition(genoclab_request, 'APPOINTMENT_PROPOSED', member)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Member proposes appointment', True,
                           f"Proposed date: {genoclab_request.appointment_date}")
        except Exception as e:
            self.record_test('GENOCLAB', 'Member proposes appointment', False, str(e))
            return

        self.assert_state(genoclab_request, 'APPOINTMENT_PROPOSED', 'GENOCLAB')

        # Step 8: Client confirms appointment
        self.log("\n  [Step 8] Client confirms appointment...")
        try:
            genoclab_request.appointment_confirmed = True
            genoclab_request.appointment_confirmed_at = timezone.now()
            genoclab_request.save()

            transition(genoclab_request, 'APPOINTMENT_CONFIRMED', client)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Client confirms appointment', True)
        except Exception as e:
            self.record_test('GENOCLAB', 'Client confirms appointment', False, str(e))
            return

        self.assert_state(genoclab_request, 'APPOINTMENT_CONFIRMED', 'GENOCLAB')

        # Step 9: Sample received and analysis workflow
        self.log("\n  [Step 9] Sample reception and analysis...")
        try:
            transition(genoclab_request, 'SAMPLE_RECEIVED', member)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Sample received', True)

            transition(genoclab_request, 'ANALYSIS_STARTED', member)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Analysis started', True)

            transition(genoclab_request, 'ANALYSIS_FINISHED', member)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Analysis finished', True)
        except Exception as e:
            self.record_test('GENOCLAB', 'Analysis workflow', False, str(e))
            return

        self.assert_state(genoclab_request, 'ANALYSIS_FINISHED', 'GENOCLAB')

        # Step 10: Payment pending
        self.log("\n  [Step 10] Payment pending...")
        try:
            transition(genoclab_request, 'PAYMENT_PENDING', member)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Payment pending', True)
        except Exception as e:
            self.record_test('GENOCLAB', 'Payment pending', False, str(e))
            return

        self.assert_state(genoclab_request, 'PAYMENT_PENDING', 'GENOCLAB')

        # Step 11: Payment confirmed
        self.log("\n  [Step 11] Payment confirmed...")
        try:
            # Upload payment receipt
            dummy_receipt = BytesIO(b"Dummy payment receipt content")
            from django.core.files.base import ContentFile
            genoclab_request.payment_receipt_file.save(
                f"payment_{genoclab_request.display_id}.pdf",
                ContentFile(dummy_receipt.read()),
                save=True
            )
            genoclab_request.payment_uploaded_at = timezone.now()
            genoclab_request.save()

            transition(genoclab_request, 'PAYMENT_CONFIRMED', admin_ops)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Payment confirmed', True,
                           f"Receipt file: {genoclab_request.payment_receipt_file.name}")
        except Exception as e:
            self.record_test('GENOCLAB', 'Payment confirmed', False, str(e))
            return

        self.assert_state(genoclab_request, 'PAYMENT_CONFIRMED', 'GENOCLAB')

        # Step 12: Report uploaded
        self.log("\n  [Step 12] Member uploads report...")
        try:
            dummy_report = BytesIO(b"%PDF-1.4 dummy report content")
            from django.core.files.base import ContentFile
            genoclab_request.report_file.save(
                f"report_{genoclab_request.display_id}.pdf",
                ContentFile(dummy_report.read()),
                save=True
            )

            transition(genoclab_request, 'REPORT_UPLOADED', member)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Report uploaded', True)
        except Exception as e:
            self.record_test('GENOCLAB', 'Report uploaded', False, str(e))
            return

        self.assert_state(genoclab_request, 'REPORT_UPLOADED', 'GENOCLAB')

        # Step 13: Admin validates report
        self.log("\n  [Step 13] Admin validates report...")
        try:
            transition(genoclab_request, 'REPORT_VALIDATED', admin_ops)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Admin validates report', True)
        except Exception as e:
            self.record_test('GENOCLAB', 'Admin validates report', False, str(e))
            return

        self.assert_state(genoclab_request, 'REPORT_VALIDATED', 'GENOCLAB')

        # Step 14: Report sent to client
        self.log("\n  [Step 14] Sending report to client...")
        try:
            transition(genoclab_request, 'SENT_TO_CLIENT', admin_ops)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Report sent to client', True)
        except Exception as e:
            self.record_test('GENOCLAB', 'Report sent to client', False, str(e))
            return

        self.assert_state(genoclab_request, 'SENT_TO_CLIENT', 'GENOCLAB')

        # Step 15: Client completes
        self.log("\n  [Step 15] Client completes...")
        try:
            genoclab_request.receipt_confirmed = True
            genoclab_request.receipt_confirmed_at = timezone.now()
            genoclab_request.service_rating = 4
            genoclab_request.rating_comment = 'Good service!'
            genoclab_request.rated_at = timezone.now()
            genoclab_request.save()

            transition(genoclab_request, 'COMPLETED', client)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Client completes and rates', True)
        except Exception as e:
            self.record_test('GENOCLAB', 'Client completes', False, str(e))
            return

        self.assert_state(genoclab_request, 'COMPLETED', 'GENOCLAB')

        # Step 16: Archive
        self.log("\n  [Step 16] Archiving request...")
        try:
            transition(genoclab_request, 'ARCHIVED', admin_ops)
            genoclab_request.refresh_from_db()
            self.record_test('GENOCLAB', 'Request archived', True)
        except Exception as e:
            self.record_test('GENOCLAB', 'Request archived', False, str(e))
            return

        self.assert_state(genoclab_request, 'ARCHIVED', 'GENOCLAB')

        # Step 17: Verify notifications
        self.log("\n  [Step 17] Verifying notifications...")
        self.verify_notifications(genoclab_request, 'GENOCLAB')

        # Step 18: Verify PDFs generated
        self.log("\n  [Step 18] Verifying PDF generation...")
        self.verify_pdfs(genoclab_request, 'GENOCLAB')

        self.log("\n  GENOCLAB Pipeline Complete!")

    def assert_state(self, request_obj, expected_state: str, channel: str):
        """Assert that the request is in the expected state."""
        actual_state = request_obj.status
        passed = actual_state == expected_state

        if not passed:
            self.record_test(f'{channel}-State', f'State validation: {expected_state}',
                           False, f'Expected {expected_state}, got {actual_state}',
                           expected_state, actual_state)
        else:
            self.record_test(f'{channel}-State', f'State: {expected_state}', True)

    def verify_notifications(self, request_obj, channel: str):
        """Verify that notifications were created for the request."""
        from notifications.models import Notification

        try:
            notifications = Notification.objects.filter(request=request_obj)
            count = notifications.count()

            # Check for specific notification types
            workflow_notifications = notifications.filter(
                notification_type='WORKFLOW'
            ).count()

            has_notifications = count > 0
            self.record_test(f'{channel}-Notifications', 'Notifications created',
                           has_notifications,
                           f"Total notifications: {count}, Workflow: {workflow_notifications}")

            # Check recipients
            recipients = set(n.user_id for n in notifications)
            self.record_test(f'{channel}-Notifications', 'Multiple recipients',
                           len(recipients) > 1,
                           f"Recipients: {len(recipients)}")

        except Exception as e:
            self.record_test(f'{channel}-Notifications', 'Verify notifications', False, str(e))

    def verify_budget_tracking(self, request_obj, requester):
        """Verify IBTIKAR budget tracking."""
        from core.financial import get_ibtikar_budget_used_by_requester, check_ibtikar_budget

        try:
            # Check budget used by requester
            budget_used = get_ibtikar_budget_used_by_requester(requester.id)
            self.record_test('IBTIKAR-Budget', 'Budget used tracked', budget_used > 0,
                           f"Budget used: {budget_used} DZD")

            # Check budget check function
            budget_check = check_ibtikar_budget(
                amount=request_obj.budget_amount,
                requester=requester
            )
            self.record_test('IBTIKAR-Budget', 'Budget check function', True,
                           f"Used: {budget_check['used']}, Cap: {budget_check['cap']}, "
                           f"Remaining: {budget_check['remaining']}")

        except Exception as e:
            self.record_test('IBTIKAR-Budget', 'Budget tracking', False, str(e))

    def verify_pdfs(self, request_obj, channel: str):
        """Verify PDFs were generated at correct stages."""
        try:
            if channel == 'IBTIKAR':
                # Check IBTIKAR form
                has_form = bool(request_obj.generated_ibtikar_form)
                self.record_test(f'{channel}-PDF', 'IBTIKAR form generated', has_form,
                               f"Form path: {request_obj.generated_ibtikar_form.name if has_form else 'N/A'}")

                # Check Platform Note
                has_note = bool(request_obj.generated_platform_note)
                self.record_test(f'{channel}-PDF', 'Platform Note generated', has_note,
                               f"Note path: {request_obj.generated_platform_note.name if has_note else 'N/A'}")

            # Check Reception Form (both channels)
            has_reception = bool(request_obj.generated_reception_form)
            self.record_test(f'{channel}-PDF', 'Reception Form generated', has_reception,
                           f"Reception path: {request_obj.generated_reception_form.name if has_reception else 'N/A'}")

            # Check report file
            has_report = bool(request_obj.report_file)
            self.record_test(f'{channel}-PDF', 'Report file exists', has_report,
                           f"Report path: {request_obj.report_file.name if has_report else 'N/A'}")

            if channel == 'GENOCLAB':
                # Check order file
                has_order = bool(request_obj.order_file)
                self.record_test(f'{channel}-PDF', 'Purchase order exists', has_order)

                # Check payment receipt
                has_payment = bool(request_obj.payment_receipt_file)
                self.record_test(f'{channel}-PDF', 'Payment receipt exists', has_payment)

        except Exception as e:
            self.record_test(f'{channel}-PDF', 'PDF verification', False, str(e))

    def print_summary(self):
        """Print comprehensive test summary."""
        self.print_header("TEST SUMMARY")

        # Group results by category
        categories = {}
        for result in self.test_results:
            cat = result['category']
            if cat not in categories:
                categories[cat] = {'passed': 0, 'failed': 0, 'total': 0}
            categories[cat]['total'] += 1
            if result['passed']:
                categories[cat]['passed'] += 1
            else:
                categories[cat]['failed'] += 1

        # Print category summaries
        self.log("\n  Category Results:", 'bold')
        total_passed = 0
        total_failed = 0

        for cat, stats in sorted(categories.items()):
            total_passed += stats['passed']
            total_failed += stats['failed']
            pass_rate = (stats['passed'] / stats['total'] * 100) if stats['total'] > 0 else 0
            color = 'success' if stats['failed'] == 0 else ('warning' if pass_rate >= 70 else 'error')
            self.log(f"    {cat:30s} {stats['passed']:3d}/{stats['total']:<3d} ({pass_rate:5.1f}%)", color)

        # Print overall summary
        total_tests = total_passed + total_failed
        overall_pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

        self.log("\n" + "=" * 70, 'header')
        self.log(f"  Total Tests: {total_tests}", 'bold')
        self.log(f"  Passed: {total_passed}", 'success')
        self.log(f"  Failed: {total_failed}", 'error' if total_failed > 0 else 'success')
        self.log(f"  Pass Rate: {overall_pass_rate:.1f}%", 'bold')
        self.log("=" * 70, 'header')

        # Print failed tests
        if total_failed > 0:
            self.log("\n  Failed Tests:", 'error')
            for result in self.test_results:
                if not result['passed']:
                    self.log(f"    - [{result['category']}] {result['test']}", 'error')
                    if result['details']:
                        self.log(f"      {result['details']}", 'info')

        # Final status
        if total_failed == 0:
            self.log("\n  ALL TESTS PASSED!", 'success')
            return True
        elif overall_pass_rate >= 80:
            self.log("\n  MOST TESTS PASSED (review failures)", 'warning')
            return True
        else:
            self.log("\n  SIGNIFICANT TEST FAILURES", 'error')
            return False

    def cleanup_test_data(self):
        """Clean up test data created during testing."""
        from core.models import Request, RequestHistory
        from notifications.models import Notification

        # Delete test requests and related data
        for key, request_obj in self.test_requests.items():
            try:
                # Delete notifications
                Notification.objects.filter(request=request_obj).delete()

                # Delete request history
                RequestHistory.objects.filter(request=request_obj).delete()

                # Delete the request
                display_id = request_obj.display_id
                request_obj.delete()
                self.log(f"  Deleted test request: {display_id}", 'info')
            except Exception as e:
                self.log(f"  Error deleting request {key}: {e}", 'warning')

        # Delete test users
        from accounts.models import User
        for key, user in self.test_users.items():
            try:
                username = user.username
                user.delete()
                self.log(f"  Deleted test user: {username}", 'info')
            except Exception as e:
                self.log(f"  Error deleting user {key}: {e}", 'warning')

        # Mark test service as inactive instead of deleting
        if hasattr(self, 'test_service'):
            try:
                self.test_service.active = False
                self.test_service.code = f"DEACTIVATED-{self.test_service.code}"
                self.test_service.save()
                self.log(f"  Deactivated test service", 'info')
            except Exception as e:
                self.log(f"  Error deactivating service: {e}", 'warning')
