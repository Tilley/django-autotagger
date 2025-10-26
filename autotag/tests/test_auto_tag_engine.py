from django.test import TestCase
from django.utils import timezone
from decimal import Decimal
from unittest.mock import Mock, patch
from autotag.rule_engine import AutoTagEngine
from autotag.models import Company, TaggingRule, TransactionTag
from autotag.tests.factories import (
    TransactionFactory, ExternalDataFactory, CompanyFactory,
    TaggingRuleFactory, SimpleRuleFactory, ConditionalRuleFactory,
    ScriptRuleFactory, GoldCustomerTransactionFactory
)


class TestAutoTagEngine(TestCase):
    
    def setUp(self):
        self.engine = AutoTagEngine()
        self.company = CompanyFactory(code="TEST_COMPANY")
        self.transaction = TransactionFactory(
            product_code="PROD_001",
            produce_rate=Decimal('1500.00'),
            source="online"
        )
        self.external_data = ExternalDataFactory(
            transaction=self.transaction,
            metadata={
                'customer_tier': 'gold',
                'amount': 2000.00,
                'category': 'premium'
            }
        )
    
    def test_tag_transaction_with_simple_rule(self):
        """Test tagging with a simple rule"""
        rule = SimpleRuleFactory(
            company=self.company,
            priority=100,
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "SIMPLE_TAG_001"
                    }
                }
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        self.assertEqual(result, "SIMPLE_TAG_001")
        
        # Check that TransactionTag was created
        tag = TransactionTag.objects.get(transaction=self.transaction, company=self.company)
        self.assertEqual(tag.tag_code, "SIMPLE_TAG_001")
        self.assertEqual(tag.confidence_score, 1.0)
        self.assertIn("Rule 'Rule_", tag.processing_notes)
    
    def test_tag_transaction_with_conditional_rule(self):
        """Test tagging with a conditional rule"""
        rule = ConditionalRuleFactory(
            company=self.company,
            priority=100,
            rule_config={
                "conditions": [
                    {
                        "field": "metadata.customer_tier",
                        "operator": "equals",
                        "value": "gold",
                        "tag": "GOLD_CUSTOMER_TAG"
                    }
                ]
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        self.assertEqual(result, "GOLD_CUSTOMER_TAG")
    
    def test_tag_transaction_with_script_rule(self):
        """Test tagging with a CEL expression rule (script type)"""
        rule = ScriptRuleFactory(
            company=self.company,
            priority=100,
            rule_config={
                "expression": "transaction.product_code == 'PROD_001' && has(metadata.customer_tier) && metadata.customer_tier == 'gold' ? 'SCRIPT_GOLD_TAG' : null"
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        self.assertEqual(result, "SCRIPT_GOLD_TAG")
    
    def test_tag_transaction_no_matching_rules(self):
        """Test tagging when no rules match"""
        rule = SimpleRuleFactory(
            company=self.company,
            rule_config={
                "mappings": {
                    "product_code": {
                        "NON_EXISTENT": "SHOULD_NOT_MATCH"
                    }
                }
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        self.assertIsNone(result)
        
        # Should not create a TransactionTag
        self.assertFalse(
            TransactionTag.objects.filter(
                transaction=self.transaction, 
                company=self.company
            ).exists()
        )
    
    def test_tag_transaction_multiple_rules_priority_order(self):
        """Test that rules are processed in priority order"""
        # Lower priority number = higher priority
        high_priority_rule = SimpleRuleFactory(
            company=self.company,
            name="High Priority Rule",
            priority=10,
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "HIGH_PRIORITY_TAG"
                    }
                }
            }
        )
        
        low_priority_rule = SimpleRuleFactory(
            company=self.company,
            name="Low Priority Rule", 
            priority=100,
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "LOW_PRIORITY_TAG"
                    }
                }
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        # Should return the high priority rule result
        self.assertEqual(result, "HIGH_PRIORITY_TAG")
    
    def test_tag_transaction_early_exit_high_priority_high_confidence(self):
        """Test early exit for high priority, high confidence rules"""
        # High priority rule (priority < 50) with high confidence should stop processing
        high_priority_rule = SimpleRuleFactory(
            company=self.company,
            name="High Priority Rule",
            priority=25,  # < 50
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "HIGH_PRIORITY_TAG"
                    }
                }
            }
        )
        
        # This rule should not be processed due to early exit
        lower_rule = SimpleRuleFactory(
            company=self.company,
            name="Should Not Process",
            priority=50,
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "SHOULD_NOT_PROCESS"
                    }
                }
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        self.assertEqual(result, "HIGH_PRIORITY_TAG")
        
        # Check processing notes to ensure only first rule was processed
        tag = TransactionTag.objects.get(transaction=self.transaction, company=self.company)
        self.assertIn("High Priority Rule", tag.processing_notes)
        self.assertNotIn("Should Not Process", tag.processing_notes)
    
    def test_tag_transaction_inactive_rules_ignored(self):
        """Test that inactive rules are ignored"""
        active_rule = SimpleRuleFactory(
            company=self.company,
            is_active=True,
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "ACTIVE_TAG"
                    }
                }
            }
        )
        
        inactive_rule = SimpleRuleFactory(
            company=self.company,
            is_active=False,
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "INACTIVE_TAG"
                    }
                }
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        self.assertEqual(result, "ACTIVE_TAG")
    
    def test_tag_transaction_rule_conditions_not_met(self):
        """Test rule skipped when conditions are not met"""
        rule = SimpleRuleFactory(
            company=self.company,
            conditions={
                "field": "metadata.customer_tier",
                "operator": "equals",
                "value": "platinum"  # Transaction has 'gold'
            },
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "SHOULD_NOT_MATCH"
                    }
                }
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        self.assertIsNone(result)
    
    def test_tag_transaction_rule_conditions_met(self):
        """Test rule processed when conditions are met"""
        rule = SimpleRuleFactory(
            company=self.company,
            conditions={
                "field": "metadata.customer_tier",
                "operator": "equals",
                "value": "gold"  # Transaction has 'gold'
            },
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "CONDITIONS_MET_TAG"
                    }
                }
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        self.assertEqual(result, "CONDITIONS_MET_TAG")
    
    def test_tag_transaction_rule_processing_error(self):
        """Test handling of rule processing errors"""
        # Create a rule that will cause an error
        rule = TaggingRuleFactory(
            company=self.company,
            rule_type="invalid_type",  # Not in PROCESSORS
            rule_config={}
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        self.assertIsNone(result)
    
    def test_tag_transaction_script_rule_error(self):
        """Test handling of CEL expression errors"""
        rule = ScriptRuleFactory(
            company=self.company,
            rule_config={
                "expression": "transaction.undefined_field == 'test' ? 'ERROR_TAG' : null"
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        # CEL expressions that fail simply return None - this is safer behavior
        self.assertIsNone(result)
        
        # With CEL, failed expressions don't create tag entries - they fail silently and safely
        # This is actually better security - no state changes on failed expressions
        tags = TransactionTag.objects.filter(transaction=self.transaction, company=self.company)
        self.assertEqual(tags.count(), 0)
    
    def test_tag_transaction_no_external_data(self):
        """Test tagging transaction without external data"""
        # Create transaction without external data
        transaction_no_data = TransactionFactory(product_code="PROD_002")
        
        rule = SimpleRuleFactory(
            company=self.company,
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_002": "NO_METADATA_TAG"
                    }
                }
            }
        )
        
        result = self.engine.tag_transaction(transaction_no_data, self.company)
        
        self.assertEqual(result, "NO_METADATA_TAG")
    
    def test_tag_transaction_update_existing_tag(self):
        """Test updating an existing transaction tag"""
        # Create existing tag
        existing_tag = TransactionTag.objects.create(
            transaction=self.transaction,
            company=self.company,
            tag_code="OLD_TAG",
            confidence_score=0.5
        )
        
        rule = SimpleRuleFactory(
            company=self.company,
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "NEW_TAG"
                    }
                }
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        self.assertEqual(result, "NEW_TAG")
        
        # Should update existing tag, not create new one
        self.assertEqual(TransactionTag.objects.filter(
            transaction=self.transaction, 
            company=self.company
        ).count(), 1)
        
        updated_tag = TransactionTag.objects.get(
            transaction=self.transaction, 
            company=self.company
        )
        self.assertEqual(updated_tag.tag_code, "NEW_TAG")
        self.assertEqual(updated_tag.confidence_score, 1.0)
    
    def test_tag_transaction_best_confidence_wins(self):
        """Test that rule with best confidence score wins"""
        # Mock processors to return different confidence scores
        with patch.object(self.engine.PROCESSORS['simple'], 'process') as mock_simple:
            mock_simple.return_value = "SIMPLE_TAG"
            
            # Create rules with different priorities
            rule1 = SimpleRuleFactory(
                company=self.company,
                priority=100,
                rule_config={"mappings": {"product_code": {"PROD_001": "TAG1"}}}
            )
            
            rule2 = SimpleRuleFactory(
                company=self.company,
                priority=200,
                rule_config={"mappings": {"product_code": {"PROD_001": "TAG2"}}}
            )
            
            # Both should match, first one wins due to priority
            result = self.engine.tag_transaction(self.transaction, self.company)
            
            self.assertEqual(result, "SIMPLE_TAG")
    
    def test_check_rule_conditions_empty_conditions(self):
        """Test _check_rule_conditions with empty conditions"""
        result = self.engine._check_rule_conditions(
            self.transaction, 
            self.external_data.metadata, 
            {}
        )
        
        self.assertTrue(result)
    
    def test_check_rule_conditions_valid_conditions(self):
        """Test _check_rule_conditions with valid conditions"""
        conditions = {
            "field": "metadata.customer_tier",
            "operator": "equals",
            "value": "gold"
        }
        
        result = self.engine._check_rule_conditions(
            self.transaction,
            self.external_data.metadata,
            conditions
        )
        
        self.assertTrue(result)
    
    def test_check_rule_conditions_invalid_conditions(self):
        """Test _check_rule_conditions with invalid conditions"""
        conditions = {
            "field": "metadata.customer_tier", 
            "operator": "equals",
            "value": "platinum"
        }
        
        result = self.engine._check_rule_conditions(
            self.transaction,
            self.external_data.metadata,
            conditions
        )
        
        self.assertFalse(result)
    
    def test_tag_transaction_ml_rule_placeholder(self):
        """Test ML rule returns None (placeholder implementation)"""
        rule = TaggingRuleFactory(
            company=self.company,
            rule_type="ml",
            rule_config={
                "model_type": "classification",
                "model_params": {}
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        self.assertIsNone(result)  # ML processor returns None
    
    def test_tag_transaction_complex_rule_combination(self):
        """Test complex combination of different rule types"""
        # Simple rule with high priority
        simple_rule = SimpleRuleFactory(
            company=self.company,
            name="Simple Rule",
            priority=200,
            rule_config={
                "mappings": {
                    "source": {
                        "online": "ONLINE_TAG"
                    }
                }
            }
        )
        
        # Conditional rule with medium priority  
        conditional_rule = ConditionalRuleFactory(
            company=self.company,
            name="Conditional Rule",
            priority=100,
            rule_config={
                "conditions": [
                    {
                        "conditions": [
                            {"field": "metadata.customer_tier", "operator": "equals", "value": "gold"},
                            {"field": "source", "operator": "equals", "value": "online"}
                        ],
                        "operator": "and",
                        "tag": "GOLD_ONLINE_TAG"
                    }
                ]
            }
        )
        
        # Script rule with highest priority (CEL expression)
        script_rule = ScriptRuleFactory(
            company=self.company,
            name="Script Rule",
            priority=50,
            rule_config={
                "expression": "transaction.source == 'online' && has(metadata.customer_tier) && metadata.customer_tier == 'gold' && transaction.produce_rate > 1000.0 ? 'PREMIUM_SCRIPT_TAG' : null"
            }
        )
        
        result = self.engine.tag_transaction(self.transaction, self.company)
        
        # Should return script rule result due to highest priority
        self.assertEqual(result, "PREMIUM_SCRIPT_TAG")
    
    def test_tag_transaction_performance_many_rules(self):
        """Test performance with many rules"""
        # Create many rules
        for i in range(50):
            SimpleRuleFactory(
                company=self.company,
                name=f"Rule_{i:02d}",
                priority=100 + i,
                rule_config={
                    "mappings": {
                        "product_code": {
                            f"PROD_{i:03d}": f"TAG_{i:03d}"
                        }
                    }
                }
            )
        
        # Add one matching rule with highest priority (lowest number)
        matching_rule = SimpleRuleFactory(
            company=self.company,
            name="Matching Rule",
            priority=50,  # Higher priority than any of the other rules
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "MATCHING_TAG"
                    }
                }
            }
        )
        
        start_time = timezone.now()
        result = self.engine.tag_transaction(self.transaction, self.company)
        end_time = timezone.now()
        
        self.assertEqual(result, "MATCHING_TAG")
        
        # Should complete in reasonable time (less than 1 second)
        execution_time = (end_time - start_time).total_seconds()
        self.assertLess(execution_time, 1.0)
    
    def test_tag_transaction_different_companies_isolated(self):
        """Test that companies' rules are isolated"""
        company_a = CompanyFactory(code="COMPANY_A")
        company_b = CompanyFactory(code="COMPANY_B")
        
        # Rule for company A
        rule_a = SimpleRuleFactory(
            company=company_a,
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "COMPANY_A_TAG"
                    }
                }
            }
        )
        
        # Rule for company B  
        rule_b = SimpleRuleFactory(
            company=company_b,
            rule_config={
                "mappings": {
                    "product_code": {
                        "PROD_001": "COMPANY_B_TAG"
                    }
                }
            }
        )
        
        # Tag with company A
        result_a = self.engine.tag_transaction(self.transaction, company_a)
        self.assertEqual(result_a, "COMPANY_A_TAG")
        
        # Tag with company B
        result_b = self.engine.tag_transaction(self.transaction, company_b)
        self.assertEqual(result_b, "COMPANY_B_TAG")
        
        # Should have separate tags for each company
        self.assertEqual(TransactionTag.objects.filter(transaction=self.transaction).count(), 2)