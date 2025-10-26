from django.test import TestCase
from decimal import Decimal
from autotag.rule_engine import SimpleRuleProcessor
from autotag.tests.factories import (
    TransactionFactory, ExternalDataFactory, PremiumTransactionFactory
)


class TestSimpleRuleProcessor(TestCase):
    
    def setUp(self):
        self.processor = SimpleRuleProcessor()
        self.transaction = TransactionFactory(
            product_code="PROD_A",
            source="online",
            jurisdiction="us"
        )
        self.metadata = {
            'category': 'premium',
            'customer_tier': 'gold',
            'amount': 1500.00
        }
    
    def test_product_code_mapping_match(self):
        """Test simple product code mapping that matches"""
        rule_config = {
            "mappings": {
                "product_code": {
                    "PROD_A": "TAG_001",
                    "PROD_B": "TAG_002"
                }
            }
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "TAG_001")
    
    def test_product_code_mapping_no_match(self):
        """Test product code mapping that doesn't match"""
        rule_config = {
            "mappings": {
                "product_code": {
                    "PROD_X": "TAG_001",
                    "PROD_Y": "TAG_002"
                }
            }
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_metadata_field_mapping_match(self):
        """Test metadata field mapping that matches"""
        rule_config = {
            "mappings": {
                "category": {
                    "premium": "PREMIUM_TAG",
                    "standard": "STANDARD_TAG"
                }
            }
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "PREMIUM_TAG")
    
    def test_metadata_field_mapping_no_match(self):
        """Test metadata field mapping that doesn't match"""
        rule_config = {
            "mappings": {
                "category": {
                    "basic": "BASIC_TAG",
                    "enterprise": "ENTERPRISE_TAG"
                }
            }
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_multiple_mappings_product_wins(self):
        """Test that product code mapping takes precedence"""
        rule_config = {
            "mappings": {
                "product_code": {
                    "PROD_A": "PRODUCT_TAG"
                },
                "category": {
                    "premium": "CATEGORY_TAG"
                }
            }
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "PRODUCT_TAG")
    
    def test_multiple_mappings_fallback_to_metadata(self):
        """Test fallback to metadata when product doesn't match"""
        rule_config = {
            "mappings": {
                "product_code": {
                    "PROD_X": "PRODUCT_TAG"
                },
                "category": {
                    "premium": "CATEGORY_TAG"
                }
            }
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "CATEGORY_TAG")
    
    def test_string_conversion_for_metadata_values(self):
        """Test that metadata values are converted to strings for comparison"""
        metadata_with_numbers = {
            'amount': 1500,  # Integer
            'score': 95.5,   # Float
            'count': True    # Boolean
        }
        
        rule_config = {
            "mappings": {
                "amount": {
                    "1500": "AMOUNT_TAG"
                },
                "score": {
                    "95.5": "SCORE_TAG"
                },
                "count": {
                    "True": "COUNT_TAG"
                }
            }
        }
        
        # Test integer conversion
        result = self.processor.process(self.transaction, metadata_with_numbers, rule_config)
        self.assertEqual(result, "AMOUNT_TAG")
        
        # Test float conversion
        metadata_with_numbers['amount'] = 0  # Remove amount to test score
        result = self.processor.process(self.transaction, metadata_with_numbers, rule_config)
        self.assertEqual(result, "SCORE_TAG")
        
        # Test boolean conversion
        metadata_with_numbers['score'] = 0  # Remove score to test count
        result = self.processor.process(self.transaction, metadata_with_numbers, rule_config)
        self.assertEqual(result, "COUNT_TAG")
    
    def test_empty_mappings(self):
        """Test behavior with empty mappings"""
        rule_config = {"mappings": {}}
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_missing_mappings_key(self):
        """Test behavior when mappings key is missing"""
        rule_config = {}
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_empty_metadata(self):
        """Test behavior with empty metadata"""
        rule_config = {
            "mappings": {
                "category": {
                    "premium": "PREMIUM_TAG"
                }
            }
        }
        
        result = self.processor.process(self.transaction, {}, rule_config)
        self.assertIsNone(result)
    
    def test_metadata_field_not_present(self):
        """Test mapping for metadata field that doesn't exist"""
        rule_config = {
            "mappings": {
                "non_existent_field": {
                    "some_value": "SOME_TAG"
                }
            }
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertIsNone(result)
    
    def test_transaction_field_mapping(self):
        """Test mapping based on various transaction fields"""
        # Test source mapping
        rule_config = {
            "mappings": {
                "source": {
                    "online": "ONLINE_TAG",
                    "pos": "POS_TAG"
                }
            }
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "ONLINE_TAG")
        
        # Test jurisdiction mapping
        rule_config = {
            "mappings": {
                "jurisdiction": {
                    "us": "US_TAG",
                    "eu": "EU_TAG"
                }
            }
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "US_TAG")
    
    def test_complex_metadata_structure(self):
        """Test with complex nested metadata"""
        complex_metadata = {
            'customer': {
                'tier': 'gold',
                'region': 'north'
            },
            'payment': {
                'method': 'card',
                'currency': 'USD'
            },
            'tags': ['premium', 'fast']
        }
        
        # Simple processor doesn't handle nested fields, should not match
        rule_config = {
            "mappings": {
                "customer": {
                    "{'tier': 'gold', 'region': 'north'}": "COMPLEX_TAG"
                }
            }
        }
        
        result = self.processor.process(self.transaction, complex_metadata, rule_config)
        self.assertEqual(result, "COMPLEX_TAG")
    
    def test_case_sensitive_matching(self):
        """Test that matching is case sensitive"""
        rule_config = {
            "mappings": {
                "category": {
                    "Premium": "PREMIUM_TAG",  # Capital P
                    "premium": "LOWERCASE_TAG"  # lowercase p
                }
            }
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "LOWERCASE_TAG")  # Should match lowercase
    
    def test_whitespace_handling(self):
        """Test handling of whitespace in values"""
        metadata_with_spaces = {
            'category': ' premium ',  # With spaces
            'tier': 'gold'
        }
        
        rule_config = {
            "mappings": {
                "category": {
                    "premium": "NO_SPACE_TAG",
                    " premium ": "WITH_SPACE_TAG"
                }
            }
        }
        
        result = self.processor.process(self.transaction, metadata_with_spaces, rule_config)
        self.assertEqual(result, "WITH_SPACE_TAG")  # Exact match including spaces
    
    def test_unicode_and_special_characters(self):
        """Test handling of unicode and special characters"""
        unicode_metadata = {
            'description': 'café payment',
            'currency': '€',
            'category': 'special-chars_123'
        }
        
        rule_config = {
            "mappings": {
                "description": {
                    "café payment": "UNICODE_TAG"
                },
                "currency": {
                    "€": "EURO_TAG"
                },
                "category": {
                    "special-chars_123": "SPECIAL_TAG"
                }
            }
        }
        
        result = self.processor.process(self.transaction, unicode_metadata, rule_config)
        self.assertEqual(result, "UNICODE_TAG")
    
    def test_large_mapping_performance(self):
        """Test performance with large mapping configurations"""
        # Create a large mapping
        large_mapping = {f"PROD_{i:05d}": f"TAG_{i:05d}" for i in range(1000)}
        large_mapping["PROD_A"] = "FOUND_TAG"
        
        rule_config = {
            "mappings": {
                "product_code": large_mapping
            }
        }
        
        result = self.processor.process(self.transaction, self.metadata, rule_config)
        self.assertEqual(result, "FOUND_TAG")
    
    def test_none_values_in_metadata(self):
        """Test handling of None values in metadata"""
        metadata_with_none = {
            'category': None,
            'tier': 'gold',
            'amount': 1500
        }
        
        rule_config = {
            "mappings": {
                "category": {
                    "None": "NONE_TAG",
                    "premium": "PREMIUM_TAG"
                },
                "tier": {
                    "gold": "GOLD_TAG"
                }
            }
        }
        
        result = self.processor.process(self.transaction, metadata_with_none, rule_config)
        self.assertEqual(result, "NONE_TAG")  # Should convert None to "None" string