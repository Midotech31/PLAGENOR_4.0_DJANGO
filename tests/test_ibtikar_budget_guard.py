# tests/test_ibtikar_budget_guard.py — PLAGENOR 4.0 IBTIKAR Smart Budget Guard Tests

import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta


pytestmark = pytest.mark.django_db


class TestSmartBudgetLogic:
    """Tests for the SMART budget guard logic in core/financial.py."""

    def test_get_ibtikar_budget_available_first_time_user(self, user_factory):
        """Test budget available for a first-time user with no previous requests."""
        from core.financial import get_ibtikar_budget_available
        
        user = user_factory.create(role='REQUESTER')
        
        result = get_ibtikar_budget_available(
            requester=user,
            declared_balance=200000,
            declared_balance_at=None
        )
        
        assert result['declared_balance'] == 200000
        assert result['consumption_since_declaration'] == 0
        assert result['available_budget'] == 200000
        assert result['exceeded'] is False

    def test_get_ibtikar_budget_available_with_previous_consumption(self, user_factory, service_factory):
        """Test budget available when user has made previous requests."""
        from core.financial import get_ibtikar_budget_available, get_ibtikar_budget_used_by_requester
        from core.models import Request
        import uuid
        
        user = user_factory.create(role='REQUESTER')
        service = service_factory.create(ibtikar_price=50000)
        
        # Create a previous request (simulating a request made earlier)
        earlier_time = timezone.now() - timedelta(days=1)
        Request.objects.create(
            title='Previous request',
            service=service,
            channel='IBTIKAR',
            status='SUBMITTED',
            requester=user,
            budget_amount=50000,
            declared_ibtikar_balance=200000,
            declared_balance_at=earlier_time,
            display_id=f'TST-{uuid.uuid4().hex[:8].upper()}',
        )
        
        # Now check budget with new declaration
        result = get_ibtikar_budget_available(
            requester=user,
            declared_balance=200000,
            declared_balance_at=earlier_time
        )
        
        # Consumption since declaration should include the 50K request
        assert result['consumption_since_declaration'] == 50000
        assert result['available_budget'] == 150000

    def test_check_ibtikar_budget_smart_mode_exceeded(self, user_factory, service_factory):
        """Test that smart budget check blocks requests exceeding available budget."""
        from core.financial import check_ibtikar_budget
        from core.models import Request
        import uuid
        
        user = user_factory.create(role='REQUESTER')
        service = service_factory.create(ibtikar_price=50000)
        
        # Create a previous request consuming 180K
        earlier_time = timezone.now() - timedelta(days=1)
        Request.objects.create(
            title='Previous high-value request',
            service=service,
            channel='IBTIKAR',
            status='SUBMITTED',
            requester=user,
            budget_amount=180000,
            declared_ibtikar_balance=200000,
            declared_balance_at=earlier_time,
            display_id=f'TST-{uuid.uuid4().hex[:8].upper()}',
        )
        
        # Try to add a new request for 30K (should fail - only 20K available)
        result = check_ibtikar_budget(
            amount=30000,
            requester=user,
            declared_balance=200000,
            declared_balance_at=earlier_time
        )
        
        assert result['smart_mode'] is True
        assert result['exceeded'] is True
        assert result['available'] == 20000
        assert 'suggested_action' in result

    def test_check_ibtikar_budget_smart_mode_ok(self, user_factory, service_factory):
        """Test that smart budget check allows requests within available budget."""
        from core.financial import check_ibtikar_budget
        from core.models import Request
        import uuid
        
        user = user_factory.create(role='REQUESTER')
        service = service_factory.create(ibtikar_price=10000)
        
        # Create a previous request consuming 50K
        earlier_time = timezone.now() - timedelta(days=1)
        Request.objects.create(
            title='Previous request',
            service=service,
            channel='IBTIKAR',
            status='SUBMITTED',
            requester=user,
            budget_amount=50000,
            declared_ibtikar_balance=200000,
            declared_balance_at=earlier_time,
            display_id=f'TST-{uuid.uuid4().hex[:8].upper()}',
        )
        
        # Try to add a new request for 30K (should pass - 150K available)
        result = check_ibtikar_budget(
            amount=30000,
            requester=user,
            declared_balance=200000,
            declared_balance_at=earlier_time
        )
        
        assert result['smart_mode'] is True
        assert result['exceeded'] is False
        assert result['available'] == 150000

    def test_check_ibtikar_budget_cap_exceeded(self, user_factory, service_factory):
        """Test that total consumption exceeding cap triggers warning."""
        from core.financial import check_ibtikar_budget
        from core.models import Request
        import uuid
        
        user = user_factory.create(role='REQUESTER')
        service = service_factory.create(ibtikar_price=50000)
        
        # Create requests totaling 210K (exceeds 200K cap)
        earlier_time = timezone.now() - timedelta(days=2)
        Request.objects.create(
            title='Request 1',
            service=service,
            channel='IBTIKAR',
            status='SUBMITTED',
            requester=user,
            budget_amount=120000,
            declared_ibtikar_balance=200000,
            declared_balance_at=earlier_time,
            display_id=f'TST-{uuid.uuid4().hex[:8].upper()}',
        )
        Request.objects.create(
            title='Request 2',
            service=service,
            channel='IBTIKAR',
            status='SUBMITTED',
            requester=user,
            budget_amount=90000,
            declared_ibtikar_balance=200000,
            declared_balance_at=earlier_time,
            display_id=f'TST-{uuid.uuid4().hex[:8].upper()}',
        )
        
        result = check_ibtikar_budget(
            amount=10000,
            requester=user,
            declared_balance=200000,
            declared_balance_at=earlier_time
        )
        
        assert result['cap_exceeded'] is True
        assert result['total_consumed'] == 210000

    def test_consumption_excludes_rejected_requests(self, user_factory, service_factory):
        """Test that rejected/cancelled requests don't count toward consumption."""
        from core.financial import get_ibtikar_budget_used_since_declaration
        from core.models import Request
        import uuid
        
        user = user_factory.create(role='REQUESTER')
        service = service_factory.create(ibtikar_price=50000)
        earlier_time = timezone.now() - timedelta(days=1)
        
        # Create rejected request (should not count)
        Request.objects.create(
            title='Rejected request',
            service=service,
            channel='IBTIKAR',
            status='REJECTED',
            requester=user,
            budget_amount=100000,
            declared_ibtikar_balance=200000,
            declared_balance_at=earlier_time,
            display_id=f'TST-{uuid.uuid4().hex[:8].upper()}',
        )
        
        # Create active request (should count)
        Request.objects.create(
            title='Active request',
            service=service,
            channel='IBTIKAR',
            status='SUBMITTED',
            requester=user,
            budget_amount=50000,
            declared_ibtikar_balance=200000,
            declared_balance_at=earlier_time,
            display_id=f'TST-{uuid.uuid4().hex[:8].upper()}',
        )
        
        consumption = get_ibtikar_budget_used_since_declaration(
            requester=user,
            declared_balance_at=earlier_time
        )
        
        assert consumption == 50000  # Only active request counts


class TestIBTIKARService:
    """Tests for the IBTIKAR service submission with budget guard."""

    def test_submit_ibtikar_request_stores_declaration(self, user_factory, service_factory):
        """Test that request submission stores declared balance and timestamp."""
        from core.services.ibtikar import submit_ibtikar_request
        
        user = user_factory.create(role='REQUESTER')
        service = service_factory.create()
        
        req = submit_ibtikar_request(
            data={
                'title': 'Test request',
                'service_id': str(service.pk),
                'budget_amount': 50000,
                'declared_ibtikar_balance': 150000,
                'service_params': {},
                'sample_table': [],
            },
            user=user
        )
        
        assert req.declared_ibtikar_balance == 150000
        assert req.declared_balance_at is not None

    def test_submit_ibtikar_request_with_budget_warning(self, user_factory, service_factory):
        """Test that budget warning is added when budget check fails.
        
        This test verifies that when the estimated cost exceeds the available budget,
        the _budget_warning is added to the data dict.
        
        Note: The SMART budget logic means consumption only counts requests made AFTER
        the student's last balance declaration. So an existing request doesn't count
        against the new submission's available budget.
        
        To test exceeded=True, we need to:
        1. Submit a new request that consumes budget
        2. Then submit another request with insufficient remaining balance
        """
        from core.services.ibtikar import submit_ibtikar_request
        from core.models import Request
        import uuid
        
        user = user_factory.create(role='REQUESTER')
        service = service_factory.create(ibtikar_price=50000)
        
        # Create existing request consuming 180K from the SAME declared balance
        # Using declared_balance_at far in the past so it's included in consumption
        old_time = timezone.now() - timedelta(days=30)
        Request.objects.create(
            title='Existing request',
            service=service,
            channel='IBTIKAR',
            status='SUBMITTED',
            requester=user,
            budget_amount=180000,
            declared_ibtikar_balance=200000,
            declared_balance_at=old_time,
            display_id=f'TST-{uuid.uuid4().hex[:8].upper()}',
        )
        
        # Submit new request for 30K when only 20K should be available
        # declared_balance_at=None means use the LAST declaration time from requests
        # The last request's declared_balance_at is old_time, so consumption includes
        # the existing 180K request, leaving only 20K available
        data = {
            'title': 'New request',
            'service_id': str(service.pk),
            'budget_amount': 30000,
            'declared_ibtikar_balance': 200000,
            'declared_balance_at': None,  # Use last declaration time
            'service_params': {},
            'sample_table': [],
        }
        
        req = submit_ibtikar_request(data=data, user=user)
        
        assert req is not None
        # With declared_balance_at=None, the function uses the old_time from the last request
        # consumption = 180K (from old request)
        # available = 200K - 180K = 20K
        # 30K > 20K → exceeded=True
        assert '_budget_warning' in data
        assert data['_budget_warning']['exceeded'] is True


class TestGetIBTIKARRequestContext:
    """Tests for the IBTIKAR request context function."""

    def test_context_returns_ibtikar_budget_data(self, user_factory):
        """Test that context returns correct budget data for IBTIKAR form."""
        from core.services.ibtikar import get_ibtikar_request_context
        
        user = user_factory.create(role='REQUESTER')
        
        context = get_ibtikar_request_context(user)
        
        assert 'declared' in context
        assert 'budget_used' in context
        assert 'available' in context
        assert 'budget_cap' in context
        assert context['budget_cap'] == 200000

    def test_context_with_previous_requests(self, user_factory, service_factory):
        """Test that context correctly calculates budget with previous requests."""
        from core.services.ibtikar import get_ibtikar_request_context
        from core.models import Request
        import uuid
        
        user = user_factory.create(role='REQUESTER')
        service = service_factory.create(ibtikar_price=50000)
        
        # Create request with declaration
        earlier_time = timezone.now() - timedelta(days=1)
        Request.objects.create(
            title='Previous request',
            service=service,
            channel='IBTIKAR',
            status='SUBMITTED',
            requester=user,
            budget_amount=50000,
            declared_ibtikar_balance=200000,
            declared_balance_at=earlier_time,
            display_id=f'TST-{uuid.uuid4().hex[:8].upper()}',
        )
        
        context = get_ibtikar_request_context(user)
        
        assert context['declared'] == 200000
        assert context['budget_used'] == 50000
        assert context['consumption_since_declaration'] == 50000
        assert context['available'] == 150000


class TestRequestModelFields:
    """Tests for Request model budget-related fields."""

    def test_declared_ibtikar_balance_field_exists(self):
        """Test that declared_ibtikar_balance field exists on Request model."""
        from core.models import Request
        
        assert hasattr(Request, 'declared_ibtikar_balance')
        
        field = Request._meta.get_field('declared_ibtikar_balance')
        assert field.get_internal_type() == 'DecimalField'

    def test_declared_balance_at_field_exists(self):
        """Test that declared_balance_at field exists on Request model."""
        from core.models import Request
        
        assert hasattr(Request, 'declared_balance_at')
        
        field = Request._meta.get_field('declared_balance_at')
        assert field.get_internal_type() == 'DateTimeField'
        assert field.null is True
        assert field.blank is True
