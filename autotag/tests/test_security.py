from django.test import TestCase
from autotag.rule_engine import CelRuleProcessor
from autotag.tests.factories import TransactionFactory, ExternalDataFactory


class CelSecurityTestCase(TestCase):
    """Test that CEL expressions provide inherent security
    
    CEL (Common Expression Language) is inherently secure:
    - Non-Turing complete (no infinite loops)
    - No file system access
    - No import capabilities
    - No dangerous function execution
    - Mathematically provable safety guarantees
    
    These tests verify CEL's built-in security rather than testing
    the old Python script security vulnerabilities.
    """
    
    def setUp(self):
        self.processor = CelRuleProcessor()
        self.transaction = TransactionFactory(
            product_code="TEST_001",
            source="online"
        )
        self.metadata = {'customer_tier': 'gold', 'amount': 1000.0}
    
    def test_cel_safe_expression_works(self):
        """Test that safe CEL expressions work correctly"""
        rule_config = {
            "expression": "transaction.product_code == 'TEST_001' ? 'SAFE_TAG' : null"
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "SAFE_TAG")
    
    def test_cel_invalid_syntax_fails_safely(self):
        """Test that invalid CEL syntax fails gracefully"""
        rule_config = {
            "expression": "invalid syntax here &&& wrong"
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)  # CEL fails safely
    
    def test_cel_no_file_access_possible(self):
        """Test that CEL cannot access files (this would be invalid syntax)"""
        rule_config = {
            "expression": "file('/etc/passwd') ? 'SHOULD_FAIL' : 'SAFE'"  # Not valid CEL
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)  # CEL rejects this syntax
    
    def test_cel_no_import_possible(self):
        """Test that CEL cannot perform imports (not valid CEL syntax)"""
        rule_config = {
            "expression": "import('os') ? 'SHOULD_FAIL' : 'SAFE'"  # Not valid CEL
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)  # CEL rejects this syntax
    
    def test_cel_complex_safe_operations(self):
        """Test that complex but safe CEL operations work"""
        rule_config = {
            "expression": "has(metadata.customer_tier) && metadata.customer_tier == 'gold' && metadata.amount > 500.0 ? 'COMPLEX_SAFE_TAG' : 'DEFAULT_TAG'"
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "COMPLEX_SAFE_TAG")