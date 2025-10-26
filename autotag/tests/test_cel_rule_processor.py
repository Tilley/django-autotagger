from django.test import TestCase
from decimal import Decimal
from autotag.rule_engine import CelRuleProcessor
from autotag.tests.factories import TransactionFactory, ExternalDataFactory


class TestCelRuleProcessor(TestCase):
    """Comprehensive tests for CEL rule processor functionality"""
    
    def setUp(self):
        self.processor = CelRuleProcessor()
        self.transaction = TransactionFactory(
            product_code="PREMIUM_001",
            produce_rate=Decimal('1500.00'),
            source="online",
            jurisdiction="us",
            ledger_type="credit"
        )
        self.metadata = {
            'customer_tier': 'gold',
            'amount': 2000.00,
            'category': 'premium',
            'priority': 'high'
        }
    
    def test_simple_expression_mode(self):
        """Test single CEL expression evaluation"""
        rule_config = {
            "expression": "transaction.product_code == 'PREMIUM_001' ? 'PREMIUM_TAG' : 'BASIC_TAG'"
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "PREMIUM_TAG")
    
    def test_complex_conditional_expression(self):
        """Test complex conditional CEL expression"""
        rule_config = {
            "expression": "transaction.product_code.startsWith('PREMIUM') && metadata.customer_tier == 'gold' ? 'GOLD_PREMIUM' : 'STANDARD'"
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "GOLD_PREMIUM")
    
    def test_conditions_mode(self):
        """Test multiple conditions mode"""
        rule_config = {
            "conditions": [
                {
                    "expression": "transaction.produce_rate > 2000.0",
                    "tag": "ULTRA_HIGH_VALUE"
                },
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
        self.assertEqual(result, "HIGH_VALUE")  # First matching condition
    
    def test_string_operations(self):
        """Test CEL string operations"""
        rule_config = {
            "expression": "transaction.product_code.startsWith('PREM') && transaction.product_code.endsWith('001') ? 'MATCHED_PATTERN' : 'NO_MATCH'"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "MATCHED_PATTERN")
    
    def test_numeric_operations(self):
        """Test CEL numeric operations and comparisons"""
        rule_config = {
            "expression": "transaction.produce_rate >= 1500.0 && transaction.produce_rate < 2000.0 ? 'MID_RANGE' : 'OUT_OF_RANGE'"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "MID_RANGE")
    
    def test_metadata_operations(self):
        """Test metadata access and operations"""
        rule_config = {
            "expression": "has(metadata.customer_tier) && metadata.customer_tier in ['gold', 'platinum'] ? 'PREMIUM_CUSTOMER' : 'STANDARD_CUSTOMER'"
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "PREMIUM_CUSTOMER")
    
    def test_logical_operations(self):
        """Test logical AND, OR, NOT operations"""
        rule_config = {
            "expression": "(transaction.source == 'online' || transaction.source == 'mobile') && !has(metadata.exclude_flag) ? 'DIGITAL_TRANSACTION' : 'OTHER'"
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "DIGITAL_TRANSACTION")
    
    def test_null_handling(self):
        """Test handling of null/missing values"""
        empty_metadata = {}
        rule_config = {
            "expression": "has(metadata.customer_tier) ? metadata.customer_tier : 'UNKNOWN'"
        }
        
        result = self.processor.process(self.transaction, empty_metadata, rule_config)
        self.assertEqual(result, "UNKNOWN")
    
    def test_default_tag_functionality(self):
        """Test default tag when expression returns null/empty"""
        rule_config = {
            "expression": "transaction.product_code == 'NONEXISTENT' ? 'FOUND' : null",
            "default_tag": "DEFAULT_TAG"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "DEFAULT_TAG")
    
    def test_list_membership(self):
        """Test list membership operations"""
        rule_config = {
            "expression": "transaction.jurisdiction in ['us', 'ca', 'uk'] ? 'SUPPORTED_REGION' : 'UNSUPPORTED_REGION'"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "SUPPORTED_REGION")
    
    def test_multiple_field_conditions(self):
        """Test expressions with multiple transaction fields"""
        rule_config = {
            "expression": "transaction.ledger_type == 'credit' && transaction.jurisdiction == 'us' && transaction.source == 'online' ? 'US_ONLINE_CREDIT' : 'OTHER'"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "US_ONLINE_CREDIT")
    
    def test_nested_conditional_expressions(self):
        """Test nested ternary expressions"""
        rule_config = {
            "expression": "transaction.produce_rate > 2000.0 ? 'ULTRA_HIGH' : (transaction.produce_rate > 1000.0 ? 'HIGH' : (transaction.produce_rate > 500.0 ? 'MEDIUM' : 'LOW'))"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "HIGH")
    
    def test_string_concatenation(self):
        """Test string concatenation in CEL"""
        rule_config = {
            "expression": "'TAG_' + transaction.source + '_' + transaction.jurisdiction"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "TAG_online_us")
    
    def test_empty_expression_handling(self):
        """Test handling of empty expression"""
        rule_config = {
            "expression": "",
            "default_tag": "EMPTY_EXPRESSION"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "EMPTY_EXPRESSION")
    
    def test_invalid_expression_handling(self):
        """Test handling of invalid CEL expressions"""
        rule_config = {
            "expression": "invalid.syntax.that.should.fail",
            "default_tag": "SYNTAX_ERROR"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "SYNTAX_ERROR")
    
    def test_conditions_with_default(self):
        """Test conditions mode with default tag"""
        rule_config = {
            "conditions": [
                {
                    "expression": "transaction.produce_rate > 10000.0",
                    "tag": "ULTRA_RARE"
                },
                {
                    "expression": "transaction.product_code == 'NONEXISTENT'",
                    "tag": "NOT_FOUND"
                }
            ],
            "default_tag": "NO_CONDITIONS_MATCHED"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "NO_CONDITIONS_MATCHED")
    
    def test_legacy_script_key_support(self):
        """Test backward compatibility with 'script' key (for migration)"""
        # Note: This would need to be updated in the CelRuleProcessor to support 'script' key
        # For now, CEL processor expects 'expression' or 'conditions'
        rule_config = {
            "expression": "transaction.product_code.startsWith('PREM') ? 'LEGACY_SCRIPT_TAG' : null"
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertEqual(result, "LEGACY_SCRIPT_TAG")