from django.test import TestCase
from decimal import Decimal
from autotag.rule_engine import ConditionalRuleProcessor
from autotag.tests.factories import TransactionFactory, ExternalDataFactory


class TestConditionalRuleProcessor(TestCase):
    
    def setUp(self):
        self.processor = ConditionalRuleProcessor()
        self.transaction = TransactionFactory(
            product_code="PROD_A",
            produce_rate=Decimal('1500.00'),
            source="online",
            jurisdiction="us",
            ledger_type="credit"
        )
        self.metadata = {
            'category': 'premium',
            'customer_tier': 'gold',
            'amount': 2000.00,
            'merchant_id': 12345,
            'payment_method': 'card'
        }
    
    def test_simple_equals_condition_match(self):
        """Test simple equals condition that matches"""
        rule_config = {
            "conditions": [
                {
                    "field": "product_code",
                    "operator": "equals",
                    "value": "PROD_A",
                    "tag": "PRODUCT_A_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "PRODUCT_A_TAG")
    
    def test_simple_equals_condition_no_match(self):
        """Test simple equals condition that doesn't match"""
        rule_config = {
            "conditions": [
                {
                    "field": "product_code",
                    "operator": "equals",
                    "value": "PROD_B",
                    "tag": "PRODUCT_B_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_not_equals_condition(self):
        """Test not_equals operator"""
        rule_config = {
            "conditions": [
                {
                    "field": "source",
                    "operator": "not_equals",
                    "value": "pos",
                    "tag": "NOT_POS_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "NOT_POS_TAG")
    
    def test_greater_than_condition(self):
        """Test greater_than operator with transaction field"""
        rule_config = {
            "conditions": [
                {
                    "field": "produce_rate",
                    "operator": "greater_than",
                    "value": 1000,
                    "tag": "HIGH_RATE_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "HIGH_RATE_TAG")
    
    def test_less_than_condition(self):
        """Test less_than operator"""
        rule_config = {
            "conditions": [
                {
                    "field": "produce_rate",
                    "operator": "less_than",
                    "value": 2000,
                    "tag": "LOW_RATE_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "LOW_RATE_TAG")
    
    def test_contains_condition(self):
        """Test contains operator"""
        rule_config = {
            "conditions": [
                {
                    "field": "product_code",
                    "operator": "contains",
                    "value": "PROD",
                    "tag": "CONTAINS_PROD_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "CONTAINS_PROD_TAG")
    
    def test_regex_condition(self):
        """Test regex operator"""
        rule_config = {
            "conditions": [
                {
                    "field": "product_code",
                    "operator": "regex",
                    "value": r"^PROD_[A-Z]$",
                    "tag": "REGEX_MATCH_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "REGEX_MATCH_TAG")
    
    def test_metadata_field_access(self):
        """Test accessing metadata fields"""
        rule_config = {
            "conditions": [
                {
                    "field": "metadata.customer_tier",
                    "operator": "equals",
                    "value": "gold",
                    "tag": "GOLD_CUSTOMER_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "GOLD_CUSTOMER_TAG")
    
    def test_metadata_numeric_comparison(self):
        """Test numeric comparisons on metadata fields"""
        rule_config = {
            "conditions": [
                {
                    "field": "metadata.amount",
                    "operator": "greater_than",
                    "value": 1500,
                    "tag": "HIGH_AMOUNT_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "HIGH_AMOUNT_TAG")
    
    def test_and_condition_all_match(self):
        """Test AND condition where all subconditions match"""
        rule_config = {
            "conditions": [
                {
                    "conditions": [
                        {"field": "source", "operator": "equals", "value": "online"},
                        {"field": "metadata.amount", "operator": "greater_than", "value": 1000}
                    ],
                    "operator": "and",
                    "tag": "ONLINE_HIGH_VALUE_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "ONLINE_HIGH_VALUE_TAG")
    
    def test_and_condition_partial_match(self):
        """Test AND condition where only some subconditions match"""
        rule_config = {
            "conditions": [
                {
                    "conditions": [
                        {"field": "source", "operator": "equals", "value": "pos"},  # Doesn't match
                        {"field": "metadata.amount", "operator": "greater_than", "value": 1000}  # Matches
                    ],
                    "operator": "and",
                    "tag": "SHOULD_NOT_MATCH"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_or_condition_some_match(self):
        """Test OR condition where some subconditions match"""
        rule_config = {
            "conditions": [
                {
                    "conditions": [
                        {"field": "source", "operator": "equals", "value": "pos"},  # Doesn't match
                        {"field": "metadata.amount", "operator": "greater_than", "value": 1000}  # Matches
                    ],
                    "operator": "or",
                    "tag": "OR_MATCH_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "OR_MATCH_TAG")
    
    def test_or_condition_none_match(self):
        """Test OR condition where no subconditions match"""
        rule_config = {
            "conditions": [
                {
                    "conditions": [
                        {"field": "source", "operator": "equals", "value": "pos"},  # Doesn't match
                        {"field": "metadata.amount", "operator": "less_than", "value": 1000}  # Doesn't match
                    ],
                    "operator": "or",
                    "tag": "SHOULD_NOT_MATCH"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_nested_conditions_complex(self):
        """Test deeply nested conditions"""
        rule_config = {
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
                        {"field": "metadata.amount", "operator": "greater_than", "value": 1500}
                    ],
                    "operator": "and",
                    "tag": "COMPLEX_NESTED_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "COMPLEX_NESTED_TAG")
    
    def test_multiple_top_level_conditions_first_match(self):
        """Test multiple top-level conditions, should return first match"""
        rule_config = {
            "conditions": [
                {
                    "field": "source",
                    "operator": "equals",
                    "value": "online",
                    "tag": "FIRST_TAG"
                },
                {
                    "field": "metadata.customer_tier",
                    "operator": "equals",
                    "value": "gold",
                    "tag": "SECOND_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "FIRST_TAG")  # Should return first match
    
    def test_invalid_operator(self):
        """Test behavior with invalid operator"""
        rule_config = {
            "conditions": [
                {
                    "field": "source",
                    "operator": "invalid_operator",
                    "value": "online",
                    "tag": "INVALID_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_missing_field(self):
        """Test condition on non-existent field"""
        rule_config = {
            "conditions": [
                {
                    "field": "non_existent_field",
                    "operator": "equals",
                    "value": "some_value",
                    "tag": "MISSING_FIELD_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_missing_metadata_field(self):
        """Test condition on non-existent metadata field"""
        rule_config = {
            "conditions": [
                {
                    "field": "metadata.non_existent",
                    "operator": "equals",
                    "value": "some_value",
                    "tag": "MISSING_METADATA_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_empty_conditions(self):
        """Test behavior with empty conditions list"""
        rule_config = {"conditions": []}
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_missing_conditions_key(self):
        """Test behavior when conditions key is missing"""
        rule_config = {}
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_decimal_comparison_precision(self):
        """Test decimal comparison with high precision"""
        # Create transaction with precise decimal
        precise_transaction = TransactionFactory(produce_rate=Decimal('1234.5678'))
        
        rule_config = {
            "conditions": [
                {
                    "field": "produce_rate",
                    "operator": "greater_than",
                    "value": 1234.5677,
                    "tag": "PRECISION_TAG"
                }
            ]
        }
        
        result = self.processor.process(precise_transaction, self.metadata, rule_config)
        self.assertEqual(result, "PRECISION_TAG")
    
    def test_string_numeric_comparison(self):
        """Test comparison between string and numeric values"""
        metadata_with_string_numbers = {
            'amount': "2000.50",  # String representation of number
            'count': "100"
        }
        
        rule_config = {
            "conditions": [
                {
                    "field": "metadata.amount",
                    "operator": "greater_than",
                    "value": 2000,
                    "tag": "STRING_NUMERIC_TAG"
                }
            ]
        }
        
        # This should not match because string "2000.50" > 2000 comparison
        result = self.processor.process(self.transaction, metadata_with_string_numbers, rule_config)
        self.assertEqual(result, "STRING_NUMERIC_TAG")
    
    def test_boolean_metadata_comparison(self):
        """Test comparison with boolean metadata values"""
        boolean_metadata = {
            'is_premium': True,
            'is_verified': False,
            'has_insurance': True
        }
        
        rule_config = {
            "conditions": [
                {
                    "field": "metadata.is_premium",
                    "operator": "equals",
                    "value": True,
                    "tag": "PREMIUM_BOOL_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, boolean_metadata, rule_config)
        self.assertEqual(result, "PREMIUM_BOOL_TAG")
    
    def test_complex_regex_patterns(self):
        """Test complex regex patterns"""
        test_cases = [
            {
                "product_code": "PREMIUM_GOLD_001",
                "pattern": r"^PREMIUM_[A-Z]+_\d+$",
                "should_match": True
            },
            {
                "product_code": "premium_gold_001",
                "pattern": r"^PREMIUM_[A-Z]+_\d+$",
                "should_match": False
            },
            {
                "product_code": "BASIC_001",
                "pattern": r".*_(GOLD|SILVER|BRONZE)_.*",
                "should_match": False
            }
        ]
        
        for case in test_cases:
            transaction = TransactionFactory(product_code=case["product_code"])
            rule_config = {
                "conditions": [
                    {
                        "field": "product_code",
                        "operator": "regex",
                        "value": case["pattern"],
                        "tag": "REGEX_TEST_TAG"
                    }
                ]
            }
            
            result = self.processor.process(transaction, self.metadata, rule_config)
            if case["should_match"]:
                self.assertEqual(result, "REGEX_TEST_TAG", 
                    f"Pattern {case['pattern']} should match {case['product_code']}")
            else:
                self.assertIsNone(result,
                    f"Pattern {case['pattern']} should not match {case['product_code']}")
    
    def test_mixed_data_types_in_conditions(self):
        """Test conditions with mixed data types"""
        mixed_metadata = {
            'amount': 1500.75,
            'count': 5,
            'status': 'active',
            'is_valid': True,
            'tags': ['premium', 'fast'],
            'config': {'level': 3}
        }
        
        rule_config = {
            "conditions": [
                {
                    "conditions": [
                        {"field": "metadata.amount", "operator": "greater_than", "value": 1500},
                        {"field": "metadata.count", "operator": "equals", "value": 5},
                        {"field": "metadata.status", "operator": "equals", "value": "active"},
                        {"field": "metadata.is_valid", "operator": "equals", "value": True}
                    ],
                    "operator": "and",
                    "tag": "MIXED_TYPES_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, mixed_metadata, rule_config)
        self.assertEqual(result, "MIXED_TYPES_TAG")
    
    def test_edge_case_empty_string_values(self):
        """Test handling of empty string values"""
        empty_string_metadata = {
            'category': '',
            'description': '   ',  # Whitespace only
            'code': 'VALID'
        }
        
        rule_config = {
            "conditions": [
                {
                    "field": "metadata.category",
                    "operator": "equals",
                    "value": "",
                    "tag": "EMPTY_STRING_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, empty_string_metadata, rule_config)
        self.assertEqual(result, "EMPTY_STRING_TAG")
    
    def test_performance_with_many_conditions(self):
        """Test performance with many conditions"""
        # Create a rule with many OR conditions
        many_conditions = []
        for i in range(100):
            many_conditions.append({
                "field": "product_code",
                "operator": "equals",
                "value": f"PROD_{i:03d}"
            })
        
        # Add our actual product code as the last condition
        many_conditions.append({
            "field": "product_code",
            "operator": "equals",
            "value": "PROD_A"
        })
        
        rule_config = {
            "conditions": [
                {
                    "conditions": many_conditions,
                    "operator": "or",
                    "tag": "PERFORMANCE_TAG"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "PERFORMANCE_TAG")
    
    def test_unknown_nested_operator(self):
        """Test behavior with unknown nested operator"""
        rule_config = {
            "conditions": [
                {
                    "conditions": [
                        {"field": "source", "operator": "equals", "value": "online"},
                        {"field": "metadata.amount", "operator": "greater_than", "value": 1000}
                    ],
                    "operator": "unknown_operator",  # Invalid operator
                    "tag": "SHOULD_NOT_MATCH"
                }
            ]
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)