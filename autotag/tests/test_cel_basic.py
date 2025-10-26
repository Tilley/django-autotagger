from django.test import TestCase
from decimal import Decimal
from autotag.rule_engine import CelRuleProcessor
from autotag.tests.factories import TransactionFactory, ExternalDataFactory


class TestCelBasic(TestCase):
    """Basic tests to verify CEL functionality"""
    
    def setUp(self):
        self.processor = CelRuleProcessor()
        self.transaction = TransactionFactory(
            product_code="PREMIUM_001",
            produce_rate=Decimal("1500.00"),
            source="online"
        )
    
    def test_simple_cel_expression(self):
        """Test basic CEL expression evaluation"""
        rule_config = {
            "expression": "transaction.product_code.startsWith('PREMIUM') ? 'PREMIUM_TAG' : 'BASIC_TAG'"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "PREMIUM_TAG")
    
    def test_cel_with_metadata(self):
        """Test CEL expression with metadata"""
        metadata = {"customer_tier": "gold"}
        rule_config = {
            "expression": "transaction.product_code.startsWith('PREMIUM') && metadata.customer_tier == 'gold' ? 'GOLD_PREMIUM' : 'STANDARD'"
        }
        
        result = self.processor.process(self.transaction, metadata, rule_config)
        self.assertEqual(result, "GOLD_PREMIUM")
    
    def test_cel_conditions_mode(self):
        """Test CEL with multiple conditions"""
        rule_config = {
            "conditions": [
                {
                    "expression": "transaction.produce_rate > 1000.0",
                    "tag": "HIGH_VALUE"
                },
                {
                    "expression": "transaction.source == 'online'",
                    "tag": "ONLINE_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "HIGH_VALUE")
    
    def test_cel_numeric_comparison(self):
        """Test CEL numeric operations"""
        rule_config = {
            "expression": "transaction.produce_rate >= 1500.0 ? 'HIGH_RATE' : 'LOW_RATE'"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "HIGH_RATE")
    
    def test_cel_default_tag(self):
        """Test CEL with default tag when expression returns false/null"""
        rule_config = {
            "expression": "transaction.product_code.startsWith('BASIC') ? 'BASIC_TAG' : ''",
            "default_tag": "DEFAULT_TAG"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "DEFAULT_TAG")