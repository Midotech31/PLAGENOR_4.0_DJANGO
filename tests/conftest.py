import pytest
import factory
import factory.django
from django.conf import settings


@pytest.fixture(scope='session')
def django_db_setup():
    """Configure database for tests."""
    settings.DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }


@pytest.fixture
def user_factory(db):
    """Factory for creating test users."""
    from accounts.models import User
    
    class UserFactory(factory.django.DjangoModelFactory):
        class Meta:
            model = User
        
        username = factory.Sequence(lambda n: f'user{n}')
        email = factory.LazyAttribute(lambda obj: f'{obj.username}@test.com')
        first_name = factory.Faker('first_name')
        last_name = factory.Faker('last_name')
        role = 'MEMBER'
        
        @classmethod
        def create_member(cls, **kwargs):
            kwargs.setdefault('role', 'MEMBER')
            return cls.create(**kwargs)
        
        @classmethod
        def create_admin(cls, **kwargs):
            kwargs.setdefault('role', 'PLATFORM_ADMIN')
            return cls.create(**kwargs)
        
        @classmethod
        def create_superadmin(cls, **kwargs):
            kwargs.setdefault('role', 'SUPER_ADMIN')
            return cls.create(**kwargs)
    
    return UserFactory


@pytest.fixture
def member_profile_factory(db, user_factory):
    """Factory for creating test member profiles."""
    from accounts.models import MemberProfile
    
    class MemberProfileFactory(factory.django.DjangoModelFactory):
        class Meta:
            model = MemberProfile
        
        user = factory.SubFactory(user_factory)
        total_points = 0
        milestone_count = 0
        milestone_level = 0
        badge_level = 0
        
        @classmethod
        def with_points(cls, points, **kwargs):
            return cls.create(total_points=points, **kwargs)
    
    return MemberProfileFactory


@pytest.fixture
def service_factory(db):
    """Factory for creating test services."""
    from core.models import Service
    import uuid
    
    class ServiceFactory(factory.django.DjangoModelFactory):
        class Meta:
            model = Service
        
        name = factory.Sequence(lambda n: f'Test Service {n}')
        code = factory.LazyFunction(lambda: f'TS-{uuid.uuid4().hex[:8].upper()}')
        channel = 'BOTH'
        is_active = True
        ibtikar_price = 1000.00
        genoclab_price = 2000.00
    
    return ServiceFactory


@pytest.fixture
def service_pricing_factory(db, service_factory):
    """Factory for creating test service pricing."""
    from core.models import ServicePricing
    from decimal import Decimal
    
    class ServicePricingFactory(factory.django.DjangoModelFactory):
        class Meta:
            model = ServicePricing
        
        service = factory.SubFactory(service_factory)
        pricing_type = 'BASE'
        channel = 'BOTH'
        amount = Decimal('1000.00')
        is_active = True
        priority = 1
    
    return ServicePricingFactory


@pytest.fixture
def request_factory(db, service_factory, user_factory, member_profile_factory):
    """Factory for creating test requests."""
    from core.models import Request
    import uuid
    
    class RequestFactory(factory.django.DjangoModelFactory):
        class Meta:
            model = Request
        
        title = factory.Sequence(lambda n: f'Test Request {n}')
        service = factory.SubFactory(service_factory)
        channel = 'IBTIKAR'
        status = 'DRAFT'
        requester = factory.SubFactory(user_factory)
        display_id = factory.LazyFunction(lambda: f'REQ-{uuid.uuid4().hex[:6].upper()}')
    
    return RequestFactory


@pytest.fixture
def notification_factory(db, user_factory):
    """Factory for creating test notifications."""
    from notifications.models import Notification
    
    class NotificationFactory(factory.django.DjangoModelFactory):
        class Meta:
            model = Notification
        
        user = factory.SubFactory(user_factory)
        message = factory.Faker('sentence')
        notification_type = 'INFO'
        read = False
    
    return NotificationFactory
