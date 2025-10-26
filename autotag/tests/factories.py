import factory
from factory.django import DjangoModelFactory
from decimal import Decimal
from django.utils import timezone
from transactions.models import Transaction, ExternalData
from autotag.models import Company, TaggingRule, TransactionTag


class TransactionFactory(DjangoModelFactory):
    class Meta:
        model = Transaction
    
    product_code = factory.Sequence(lambda n: f"PROD_{n:03d}")
    produce_rate = factory.Faker('pydecimal', left_digits=3, right_digits=2, positive=True)
    ledger_type = factory.Faker('random_element', elements=['debit', 'credit'])
    source = factory.Faker('random_element', elements=['online', 'pos', 'mobile', 'bank', 'cash'])
    jurisdiction = factory.Faker('random_element', elements=['us', 'ca', 'uk', 'eu', 'au'])
    created_at = factory.Faker('date_time_this_year', tzinfo=timezone.get_current_timezone())


class ExternalDataFactory(DjangoModelFactory):
    class Meta:
        model = ExternalData
    
    transaction = factory.SubFactory(TransactionFactory)
    metadata = factory.LazyFunction(lambda: {
        'customer_id': factory.Faker('uuid4').generate(),
        'amount': float(factory.Faker('pydecimal', left_digits=4, right_digits=2, positive=True).generate()),
        'category': factory.Faker('random_element', elements=['premium', 'standard', 'basic']).generate(),
        'customer_tier': factory.Faker('random_element', elements=['gold', 'silver', 'bronze']).generate(),
        'merchant_id': factory.Faker('random_int', min=1000, max=9999).generate(),
        'payment_method': factory.Faker('random_element', elements=['card', 'bank', 'digital']).generate(),
    })


class CompanyFactory(DjangoModelFactory):
    class Meta:
        model = Company
    
    name = factory.Faker('company')
    code = factory.Sequence(lambda n: f"COMP_{n:03d}")
    metadata_schema = factory.LazyFunction(lambda: {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string"},
            "amount": {"type": "number"},
            "category": {"type": "string"},
            "customer_tier": {"type": "string"}
        }
    })
    is_active = True


class TaggingRuleFactory(DjangoModelFactory):
    class Meta:
        model = TaggingRule
    
    company = factory.SubFactory(CompanyFactory)
    name = factory.Sequence(lambda n: f"Rule_{n:03d}")
    rule_type = 'simple'
    priority = 100
    rule_config = factory.LazyFunction(lambda: {
        "mappings": {
            "product_code": {
                "PROD_001": "TAG_001",
                "PROD_002": "TAG_002"
            }
        }
    })
    conditions = factory.LazyFunction(dict)
    is_active = True


class TransactionTagFactory(DjangoModelFactory):
    class Meta:
        model = TransactionTag
    
    transaction = factory.SubFactory(TransactionFactory)
    company = factory.SubFactory(CompanyFactory)
    tag_code = factory.Sequence(lambda n: f"TAG_{n:03d}")
    confidence_score = 1.0
    is_manual_override = False
    processing_notes = factory.Faker('text', max_nb_chars=100)


# Specialized factories for different scenarios
class PremiumTransactionFactory(TransactionFactory):
    product_code = "PREMIUM_001"
    produce_rate = Decimal('1000.00')
    source = "online"


class HighValueTransactionFactory(TransactionFactory):
    produce_rate = Decimal('5000.00')


class GoldCustomerTransactionFactory(TransactionFactory):
    external_data = factory.RelatedFactory(
        'autotag.tests.factories.GoldCustomerExternalDataFactory',
        'transaction'
    )


class GoldCustomerExternalDataFactory(ExternalDataFactory):
    metadata = factory.LazyFunction(lambda: {
        'customer_tier': 'gold',
        'amount': 2500.00,
        'category': 'premium',
        'payment_method': 'card'
    })


class SimpleRuleFactory(TaggingRuleFactory):
    rule_type = 'simple'
    rule_config = factory.LazyFunction(lambda: {
        "mappings": {
            "product_code": {
                "PROD_001": "SIMPLE_TAG_001",
                "PROD_002": "SIMPLE_TAG_002",
                "PREMIUM_001": "PREMIUM_TAG"
            },
            "source": {
                "online": "ONLINE_TAG",
                "pos": "POS_TAG"
            }
        }
    })


class ConditionalRuleFactory(TaggingRuleFactory):
    rule_type = 'conditional'
    rule_config = factory.LazyFunction(lambda: {
        "conditions": [
            {
                "field": "produce_rate",
                "operator": "greater_than",
                "value": 1000,
                "tag": "HIGH_VALUE"
            },
            {
                "conditions": [
                    {"field": "source", "operator": "equals", "value": "online"},
                    {"field": "metadata.amount", "operator": "greater_than", "value": 500}
                ],
                "operator": "and",
                "tag": "HIGH_VALUE_ONLINE"
            }
        ]
    })


class ScriptRuleFactory(TaggingRuleFactory):
    rule_type = 'script'
    rule_config = factory.LazyFunction(lambda: {
        "script": '''def get_tag(transaction, metadata):
    if transaction.product_code.startswith('PREMIUM'):
        if metadata.get('customer_tier') == 'gold':
            return 'GOLD_PREMIUM'
        else:
            return 'STANDARD_PREMIUM'
    return None'''
    })


class MLRuleFactory(TaggingRuleFactory):
    rule_type = 'ml'
    rule_config = factory.LazyFunction(lambda: {
        "model_type": "classification",
        "model_params": {"algorithm": "random_forest"},
        "feature_mapping": {
            "amount": "metadata.amount",
            "customer_tier": "metadata.customer_tier"
        }
    })


class ComplexConditionalRuleFactory(TaggingRuleFactory):
    rule_type = 'conditional'
    rule_config = factory.LazyFunction(lambda: {
        "conditions": [
            {
                "conditions": [
                    {
                        "conditions": [
                            {"field": "source", "operator": "equals", "value": "online"},
                            {"field": "jurisdiction", "operator": "equals", "value": "us"}
                        ],
                        "operator": "and"
                    },
                    {"field": "metadata.amount", "operator": "greater_than", "value": 1000}
                ],
                "operator": "and",
                "tag": "US_ONLINE_HIGH_VALUE"
            },
            {
                "conditions": [
                    {"field": "metadata.customer_tier", "operator": "equals", "value": "gold"},
                    {"field": "product_code", "operator": "regex", "value": "^PREMIUM.*"}
                ],
                "operator": "and",
                "tag": "GOLD_PREMIUM_PRODUCT"
            }
        ]
    })