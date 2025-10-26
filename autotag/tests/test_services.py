from django.test import TestCase
from django.db import models
from decimal import Decimal
from autotag.services import AutoTagService
from autotag.models import Company, TaggingRule, TransactionTag
from transactions.models import Transaction, ExternalData
from autotag.tests.factories import (
    TransactionFactory, ExternalDataFactory, CompanyFactory,
    TaggingRuleFactory, SimpleRuleFactory
)


class TestAutoTagService(TestCase):
    """Test the AutoTagService business logic layer"""
    
    def setUp(self):
        self.service = AutoTagService()
        self.company = CompanyFactory(code="SERVICE_TEST_CO")
        self.transactions = [
            TransactionFactory(product_code=f"PROD_{i:03d}")
            for i in range(5)
        ]
        
        # Add external data to transactions
        for i, txn in enumerate(self.transactions):
            ExternalDataFactory(
                transaction=txn,
                metadata={
                    'customer_tier': ['bronze', 'silver', 'gold'][i % 3],
                    'amount': 1000 + (i * 500),
                    'region': ['north', 'south'][i % 2]
                }
            )
    
    def test_tag_single_transaction_success(self):
        """Test successful single transaction tagging"""
        # Create rule
        rule = SimpleRuleFactory(
            company=self.company,
            rule_config={
                'mappings': {
                    'product_code': {
                        'PROD_000': 'SINGLE_TAG_SUCCESS'
                    }
                }
            }
        )
        
        result = self.service.tag_single_transaction(
            self.transactions[0].id,
            self.company.code
        )
        
        self.assertEqual(result, 'SINGLE_TAG_SUCCESS')
        
        # Verify tag was created
        tag = TransactionTag.objects.get(
            transaction=self.transactions[0],
            company=self.company
        )
        self.assertEqual(tag.tag_code, 'SINGLE_TAG_SUCCESS')
    
    def test_tag_single_transaction_not_found(self):
        """Test tagging non-existent transaction"""
        result = self.service.tag_single_transaction(
            99999,  # Non-existent ID
            self.company.code
        )
        
        self.assertIsNone(result)
    
    def test_tag_single_transaction_company_not_found(self):
        """Test tagging with non-existent company"""
        result = self.service.tag_single_transaction(
            self.transactions[0].id,
            "NON_EXISTENT_COMPANY"
        )
        
        self.assertIsNone(result)
    
    def test_tag_single_transaction_inactive_company(self):
        """Test tagging with inactive company"""
        inactive_company = CompanyFactory(code="INACTIVE_CO", is_active=False)
        
        result = self.service.tag_single_transaction(
            self.transactions[0].id,
            inactive_company.code
        )
        
        self.assertIsNone(result)
    
    def test_tag_multiple_transactions_success(self):
        """Test successful multiple transaction tagging"""
        # Create rules for different products
        for i in range(3):
            SimpleRuleFactory(
                company=self.company,
                name=f"Multi Rule {i}",
                rule_config={
                    'mappings': {
                        'product_code': {
                            f'PROD_{i:03d}': f'MULTI_TAG_{i:03d}'
                        }
                    }
                }
            )
        
        transaction_ids = [txn.id for txn in self.transactions[:3]]
        results = self.service.tag_multiple_transactions(
            transaction_ids,
            self.company.code
        )
        
        self.assertEqual(len(results), 3)
        
        for i in range(3):
            self.assertEqual(results[self.transactions[i].id], f'MULTI_TAG_{i:03d}')
    
    def test_tag_multiple_transactions_batch_processing(self):
        """Test batch processing of multiple transactions"""
        # Create rule that matches all products
        SimpleRuleFactory(
            company=self.company,
            rule_config={
                'mappings': {
                    'product_code': {
                        f'PROD_{i:03d}': f'BATCH_TAG_{i:03d}'
                        for i in range(5)
                    }
                }
            }
        )
        
        transaction_ids = [txn.id for txn in self.transactions]
        
        # Test with small batch size
        results = self.service.tag_multiple_transactions(
            transaction_ids,
            self.company.code,
            batch_size=2
        )
        
        self.assertEqual(len(results), 5)
        
        # Verify all transactions were tagged
        for i, txn in enumerate(self.transactions):
            self.assertEqual(results[txn.id], f'BATCH_TAG_{i:03d}')
    
    def test_tag_multiple_transactions_company_not_found(self):
        """Test multiple tagging with non-existent company"""
        transaction_ids = [txn.id for txn in self.transactions]
        results = self.service.tag_multiple_transactions(
            transaction_ids,
            "NON_EXISTENT_COMPANY"
        )
        
        self.assertEqual(results, {})
    
    def test_tag_multiple_transactions_mixed_results(self):
        """Test multiple tagging with some matching, some not"""
        # Create rule that only matches some products
        SimpleRuleFactory(
            company=self.company,
            rule_config={
                'mappings': {
                    'product_code': {
                        'PROD_000': 'MATCHED_TAG_000',
                        'PROD_002': 'MATCHED_TAG_002'
                        # PROD_001, PROD_003, PROD_004 won't match
                    }
                }
            }
        )
        
        transaction_ids = [txn.id for txn in self.transactions]
        results = self.service.tag_multiple_transactions(
            transaction_ids,
            self.company.code
        )
        
        self.assertEqual(len(results), 5)
        self.assertEqual(results[self.transactions[0].id], 'MATCHED_TAG_000')
        self.assertIsNone(results[self.transactions[1].id])
        self.assertEqual(results[self.transactions[2].id], 'MATCHED_TAG_002')
        self.assertIsNone(results[self.transactions[3].id])
        self.assertIsNone(results[self.transactions[4].id])
    
    def test_retag_company_transactions(self):
        """Test re-tagging existing company transactions"""
        # Create initial tags
        for i, txn in enumerate(self.transactions[:3]):
            TransactionTag.objects.create(
                transaction=txn,
                company=self.company,
                tag_code=f'OLD_TAG_{i}',
                confidence_score=0.5
            )
        
        # Create new rule
        SimpleRuleFactory(
            company=self.company,
            rule_config={
                'mappings': {
                    'product_code': {
                        f'PROD_{i:03d}': f'NEW_TAG_{i:03d}'
                        for i in range(3)
                    }
                }
            }
        )
        
        count = self.service.retag_company_transactions(self.company.code)
        
        self.assertEqual(count, 3)
        
        # Verify tags were updated
        for i in range(3):
            tag = TransactionTag.objects.get(
                transaction=self.transactions[i],
                company=self.company
            )
            self.assertEqual(tag.tag_code, f'NEW_TAG_{i:03d}')
            self.assertEqual(tag.confidence_score, 1.0)  # Updated confidence
    
    def test_retag_company_transactions_company_not_found(self):
        """Test re-tagging with non-existent company"""
        count = self.service.retag_company_transactions("NON_EXISTENT")
        self.assertEqual(count, 0)
    
    def test_create_or_update_rule_new_rule(self):
        """Test creating a new rule"""
        rule_config = {
            'mappings': {
                'product_code': {
                    'TEST_PROD': 'TEST_TAG'
                }
            }
        }
        
        rule = self.service.create_or_update_rule(
            company_code=self.company.code,
            rule_name="New Test Rule",
            rule_type="simple",
            rule_config=rule_config,
            priority=50,
            conditions={'test': 'condition'},
            is_active=True
        )
        
        self.assertIsNotNone(rule.id)
        self.assertEqual(rule.company, self.company)
        self.assertEqual(rule.name, "New Test Rule")
        self.assertEqual(rule.rule_type, "simple")
        self.assertEqual(rule.rule_config, rule_config)
        self.assertEqual(rule.priority, 50)
        self.assertEqual(rule.conditions, {'test': 'condition'})
        self.assertTrue(rule.is_active)
    
    def test_create_or_update_rule_update_existing(self):
        """Test updating an existing rule"""
        # Create initial rule
        existing_rule = TaggingRuleFactory(
            company=self.company,
            name="Existing Rule",
            rule_type="simple",
            priority=100
        )
        
        new_config = {
            'mappings': {
                'updated_field': {
                    'updated_value': 'UPDATED_TAG'
                }
            }
        }
        
        updated_rule = self.service.create_or_update_rule(
            company_code=self.company.code,
            rule_name="Existing Rule",  # Same name
            rule_type="conditional",    # Different type
            rule_config=new_config,
            priority=25
        )
        
        # Should be the same rule object, updated
        self.assertEqual(updated_rule.id, existing_rule.id)
        self.assertEqual(updated_rule.rule_type, "conditional")
        self.assertEqual(updated_rule.rule_config, new_config)
        self.assertEqual(updated_rule.priority, 25)
    
    def test_create_or_update_rule_company_not_found(self):
        """Test creating rule with non-existent company"""
        with self.assertRaises(Company.DoesNotExist):
            self.service.create_or_update_rule(
                company_code="NON_EXISTENT",
                rule_name="Test Rule",
                rule_type="simple",
                rule_config={}
            )
    
    def test_get_tagging_stats_success(self):
        """Test getting tagging statistics"""
        # Create some tagged and untagged transactions
        tagged_transactions = self.transactions[:3]
        untagged_transactions = self.transactions[3:]
        
        # Create tags for some transactions
        for i, txn in enumerate(tagged_transactions):
            tag_code = ['TAG_A', 'TAG_B', 'TAG_A'][i]  # TAG_A appears twice
            TransactionTag.objects.create(
                transaction=txn,
                company=self.company,
                tag_code=tag_code
            )
        
        # Create tags for untagged transactions but with no tag_code
        for txn in untagged_transactions:
            TransactionTag.objects.create(
                transaction=txn,
                company=self.company,
                tag_code=None  # Untagged
            )
        
        # Create some rules
        TaggingRuleFactory(company=self.company, is_active=True)
        TaggingRuleFactory(company=self.company, is_active=True)
        TaggingRuleFactory(company=self.company, is_active=False)
        
        stats = self.service.get_tagging_stats(self.company.code)
        
        self.assertEqual(stats['total_transactions'], 5)
        self.assertEqual(stats['tagged_transactions'], 3)
        self.assertEqual(stats['untagged_transactions'], 2)
        self.assertEqual(stats['tagging_rate'], 60.0)  # 3/5 * 100
        self.assertEqual(stats['top_tags']['TAG_A'], 2)
        self.assertEqual(stats['top_tags']['TAG_B'], 1)
        self.assertEqual(stats['active_rules'], 2)
    
    def test_get_tagging_stats_company_not_found(self):
        """Test getting stats for non-existent company"""
        stats = self.service.get_tagging_stats("NON_EXISTENT")
        self.assertEqual(stats, {})
    
    def test_get_tagging_stats_no_transactions(self):
        """Test getting stats when no transactions exist"""
        empty_company = CompanyFactory(code="EMPTY_CO")
        
        stats = self.service.get_tagging_stats(empty_company.code)
        
        self.assertEqual(stats['total_transactions'], 0)
        self.assertEqual(stats['tagged_transactions'], 0)
        self.assertEqual(stats['untagged_transactions'], 0)
        self.assertEqual(stats['tagging_rate'], 0)
        self.assertEqual(stats['top_tags'], {})
    
    def test_get_tagging_stats_top_tags_limit(self):
        """Test that top tags are limited to 10"""
        # Create 15 different tags
        for i in range(15):
            TransactionTag.objects.create(
                transaction=self.transactions[0],  # Reuse transaction
                company=CompanyFactory(code=f"CO_{i}"),  # Different companies
                tag_code=f'TAG_{i:02d}'
            )
        
        # Create 15 tags for our test company
        test_transactions = [
            TransactionFactory() for _ in range(15)
        ]
        
        for i, txn in enumerate(test_transactions):
            TransactionTag.objects.create(
                transaction=txn,
                company=self.company,
                tag_code=f'TEST_TAG_{i:02d}'
            )
        
        stats = self.service.get_tagging_stats(self.company.code)
        
        # Should only return top 10 tags
        self.assertLessEqual(len(stats['top_tags']), 10)
    
    def test_service_with_different_rule_types(self):
        """Test service with different rule types working together"""
        # Create rules of different types
        simple_rule = SimpleRuleFactory(
            company=self.company,
            name="Simple Rule",
            priority=100,
            rule_config={
                'mappings': {
                    'product_code': {
                        'PROD_000': 'SIMPLE_TAG'
                    }
                }
            }
        )
        
        conditional_rule = TaggingRuleFactory(
            company=self.company,
            name="Conditional Rule",
            rule_type="conditional",
            priority=50,  # Higher priority
            rule_config={
                'conditions': [
                    {
                        'field': 'metadata.customer_tier',
                        'operator': 'equals',
                        'value': 'bronze',
                        'tag': 'CONDITIONAL_TAG'
                    }
                ]
            }
        )
        
        script_rule = TaggingRuleFactory(
            company=self.company,
            name="Script Rule",
            rule_type="script",
            priority=25,  # Highest priority
            rule_config={
                'expression': "transaction.product_code == 'PROD_000' && has(metadata.customer_tier) && metadata.customer_tier == 'bronze' ? 'SCRIPT_TAG' : null"
            }
        )
        
        # First transaction should match script rule (highest priority)
        result = self.service.tag_single_transaction(
            self.transactions[0].id,
            self.company.code
        )
        
        self.assertEqual(result, 'SCRIPT_TAG')
    
    def test_service_error_handling_in_batch_processing(self):
        """Test error handling during batch processing"""
        # Create a rule that might cause issues
        TaggingRuleFactory(
            company=self.company,
            rule_type="script",
            rule_config={
                'script': '''def get_tag(transaction, metadata):
    # This will fail for even-numbered products
    if int(transaction.product_code.split('_')[1]) % 2 == 0:
        raise ValueError("Simulated error")
    return 'SUCCESS_TAG'
'''
            }
        )
        
        transaction_ids = [txn.id for txn in self.transactions]
        results = self.service.tag_multiple_transactions(
            transaction_ids,
            self.company.code
        )
        
        # Should handle errors gracefully and process what it can
        self.assertEqual(len(results), 5)
        
        # Odd-numbered products should succeed, even-numbered should fail
        self.assertIsNone(results[self.transactions[0].id])  # PROD_000 (even)
        self.assertEqual(results[self.transactions[1].id], 'SUCCESS_TAG')  # PROD_001 (odd)
        self.assertIsNone(results[self.transactions[2].id])  # PROD_002 (even)
        self.assertEqual(results[self.transactions[3].id], 'SUCCESS_TAG')  # PROD_003 (odd)
        self.assertIsNone(results[self.transactions[4].id])  # PROD_004 (even)