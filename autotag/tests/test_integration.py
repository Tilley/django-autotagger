from django.test import TestCase, TransactionTestCase
from django.db import transaction
from django.core.management import call_command
from decimal import Decimal
import json
from io import StringIO
from autotag.models import Company, TaggingRule, TransactionTag
from autotag.services import AutoTagService
from autotag.utils import import_rules_from_json, export_rules_to_json
from transactions.models import Transaction, ExternalData
from autotag.tests.factories import (
    TransactionFactory, ExternalDataFactory, CompanyFactory,
    TaggingRuleFactory
)


class TestFullIntegration(TransactionTestCase):
    """Full integration tests covering end-to-end scenarios"""
    
    def setUp(self):
        self.company = CompanyFactory(
            code="INTEGRATION_CO",
            name="Integration Test Company"
        )
        self.service = AutoTagService()
    
    def test_complete_tagging_workflow(self):
        """Test complete workflow from transaction creation to tagging"""
        # 1. Create transactions with various characteristics
        transactions_data = [
            {
                'product_code': 'PREMIUM_001',
                'produce_rate': Decimal('2500.00'),
                'source': 'online',
                'jurisdiction': 'us',
                'metadata': {
                    'customer_tier': 'gold',
                    'amount': 3000.00,
                    'category': 'investment'
                }
            },
            {
                'product_code': 'STANDARD_002',
                'produce_rate': Decimal('750.00'),
                'source': 'pos',
                'jurisdiction': 'ca',
                'metadata': {
                    'customer_tier': 'silver',
                    'amount': 800.00,
                    'category': 'retail'
                }
            },
            {
                'product_code': 'BASIC_003',
                'produce_rate': Decimal('200.00'),
                'source': 'mobile',
                'jurisdiction': 'uk',
                'metadata': {
                    'customer_tier': 'bronze',
                    'amount': 250.00,
                    'category': 'subscription'
                }
            }
        ]
        
        transactions = []
        for data in transactions_data:
            txn = TransactionFactory(
                product_code=data['product_code'],
                produce_rate=data['produce_rate'],
                source=data['source'],
                jurisdiction=data['jurisdiction']
            )
            ExternalDataFactory(
                transaction=txn,
                metadata=data['metadata']
            )
            transactions.append(txn)
        
        # 2. Create comprehensive rule set
        rules_data = [
            {
                'name': 'Premium Product Rule',
                'rule_type': 'simple',
                'priority': 10,
                'rule_config': {
                    'mappings': {
                        'product_code': {
                            'PREMIUM_001': 'PREMIUM_PRODUCT'
                        }
                    }
                },
                'is_active': True
            },
            {
                'name': 'High Value Gold Customer',
                'rule_type': 'conditional',
                'priority': 20,
                'rule_config': {
                    'conditions': [
                        {
                            'conditions': [
                                {'field': 'metadata.customer_tier', 'operator': 'equals', 'value': 'gold'},
                                {'field': 'metadata.amount', 'operator': 'greater_than', 'value': 2000}
                            ],
                            'operator': 'and',
                            'tag': 'HIGH_VALUE_GOLD'
                        }
                    ]
                },
                'is_active': True
            },
            {
                'name': 'Geographic Routing',
                'rule_type': 'conditional',
                'priority': 30,
                'rule_config': {
                    'conditions': [
                        {
                            'field': 'jurisdiction',
                            'operator': 'equals',
                            'value': 'us',
                            'tag': 'US_TRANSACTION'
                        },
                        {
                            'field': 'jurisdiction', 
                            'operator': 'equals',
                            'value': 'ca',
                            'tag': 'CA_TRANSACTION'
                        }
                    ]
                },
                'is_active': True
            },
            {
                'name': 'Complex Business Logic',
                'rule_type': 'script',
                'priority': 50,
                'rule_config': {
                    'script': '''def get_tag(transaction, metadata):
    # Complex scoring algorithm
    score = 0
    
    # Base score from produce rate
    if float(transaction.produce_rate) > 2000:
        score += 30
    elif float(transaction.produce_rate) > 1000:
        score += 20
    elif float(transaction.produce_rate) > 500:
        score += 10
    
    # Customer tier bonus
    tier_bonus = {
        'gold': 25,
        'silver': 15,
        'bronze': 5
    }
    score += tier_bonus.get(metadata.get('customer_tier', ''), 0)
    
    # Channel bonus
    if transaction.source == 'online':
        score += 10
    elif transaction.source == 'mobile':
        score += 5
    
    # Amount bonus
    amount = metadata.get('amount', 0)
    if amount > 2000:
        score += 15
    elif amount > 1000:
        score += 10
    
    # Category bonus
    if metadata.get('category') == 'investment':
        score += 20
    
    # Determine tier based on score
    if score >= 80:
        return 'PLATINUM_TIER'
    elif score >= 60:
        return 'GOLD_TIER'
    elif score >= 40:
        return 'SILVER_TIER'
    elif score >= 20:
        return 'BRONZE_TIER'
    else:
        return 'BASIC_TIER'
'''
                },
                'is_active': True
            }
        ]
        
        # Create rules
        for rule_data in rules_data:
            TaggingRuleFactory(
                company=self.company,
                name=rule_data['name'],
                rule_type=rule_data['rule_type'],
                priority=rule_data['priority'],
                rule_config=rule_data['rule_config'],
                is_active=rule_data['is_active']
            )
        
        # 3. Tag all transactions
        transaction_ids = [txn.id for txn in transactions]
        results = self.service.tag_multiple_transactions(
            transaction_ids, 
            self.company.code
        )
        
        # 4. Verify results
        self.assertEqual(len(results), 3)
        
        # Check first transaction (Premium, Gold, High Value)
        tag1 = TransactionTag.objects.get(
            transaction=transactions[0], 
            company=self.company
        )
        self.assertEqual(tag1.tag_code, 'PREMIUM_PRODUCT')  # Highest priority rule
        
        # Check second transaction (Standard, Silver, Medium Value)
        tag2 = TransactionTag.objects.get(
            transaction=transactions[1],
            company=self.company
        )
        self.assertEqual(tag2.tag_code, 'CA_TRANSACTION')  # Geographic rule
        
        # Check third transaction (Basic, Bronze, Low Value)
        tag3 = TransactionTag.objects.get(
            transaction=transactions[2],
            company=self.company
        )
        # Should fall through to script rule
        self.assertIn(tag3.tag_code, ['BRONZE_TIER', 'SILVER_TIER', 'BASIC_TIER'])
        
        # 5. Get statistics
        stats = self.service.get_tagging_stats(self.company.code)
        self.assertEqual(stats['total_transactions'], 3)
        self.assertEqual(stats['tagged_transactions'], 3)
        self.assertEqual(stats['tagging_rate'], 100.0)
    
    def test_rule_import_export_workflow(self):
        """Test importing and exporting rules"""
        # 1. Create initial rules
        initial_rules = [
            TaggingRuleFactory(
                company=self.company,
                name="Export Test Rule 1",
                rule_type="simple",
                rule_config={'mappings': {'product_code': {'TEST_001': 'EXPORT_TAG_1'}}}
            ),
            TaggingRuleFactory(
                company=self.company,
                name="Export Test Rule 2", 
                rule_type="conditional",
                rule_config={
                    'conditions': [
                        {
                            'field': 'source',
                            'operator': 'equals',
                            'value': 'online',
                            'tag': 'EXPORT_TAG_2'
                        }
                    ]
                }
            )
        ]
        
        # 2. Export rules
        exported_json = export_rules_to_json(self.company.code)
        exported_data = json.loads(exported_json)
        
        self.assertEqual(exported_data['company_code'], self.company.code)
        self.assertEqual(len(exported_data['rules']), 2)
        
        # 3. Create new company and import rules
        new_company = CompanyFactory(code="IMPORT_TEST_CO")
        
        # Modify the exported data for the new company
        exported_data['company_code'] = new_company.code
        modified_json = json.dumps(exported_data)
        
        # Import rules
        results = import_rules_from_json(modified_json)
        
        self.assertEqual(results['imported'], 2)
        self.assertEqual(len(results.get('errors', [])), 0)
        
        # 4. Verify imported rules
        imported_rules = TaggingRule.objects.filter(company=new_company)
        self.assertEqual(imported_rules.count(), 2)
        
        # Test that imported rules work
        test_transaction = TransactionFactory(product_code="TEST_001")
        
        service = AutoTagService()
        result = service.tag_single_transaction(test_transaction.id, new_company.code)
        self.assertEqual(result, "EXPORT_TAG_1")
    
    def test_management_command_integration(self):
        """Test management commands work end-to-end"""
        # Create test transactions
        transactions = [
            TransactionFactory(product_code="CMD_TEST_001"),
            TransactionFactory(product_code="CMD_TEST_002"),
            TransactionFactory(product_code="CMD_TEST_003")
        ]
        
        # Create external data
        for txn in transactions:
            ExternalDataFactory(
                transaction=txn,
                metadata={'test_field': 'test_value'}
            )
        
        # Create rules
        TaggingRuleFactory(
            company=self.company,
            rule_config={
                'mappings': {
                    'product_code': {
                        'CMD_TEST_001': 'CMD_TAG_001',
                        'CMD_TEST_002': 'CMD_TAG_002',
                        'CMD_TEST_003': 'CMD_TAG_003'
                    }
                }
            }
        )
        
        # Test tag_transactions command
        out = StringIO()
        call_command(
            'tag_transactions',
            self.company.code,
            '--transaction-ids',
            str(transactions[0].id),
            str(transactions[1].id),
            stdout=out
        )
        
        output = out.getvalue()
        self.assertIn('Tagged 2/2 transactions', output)
        
        # Verify tags were created
        self.assertTrue(
            TransactionTag.objects.filter(
                transaction=transactions[0],
                company=self.company,
                tag_code='CMD_TAG_001'
            ).exists()
        )
        
        self.assertTrue(
            TransactionTag.objects.filter(
                transaction=transactions[1],
                company=self.company,
                tag_code='CMD_TAG_002'
            ).exists()
        )
    
    def test_multi_company_isolation(self):
        """Test that multiple companies can tag the same transactions differently"""
        # Create shared transactions
        shared_transaction = TransactionFactory(
            product_code="SHARED_001",
            source="online"
        )
        ExternalDataFactory(
            transaction=shared_transaction,
            metadata={'customer_type': 'premium'}
        )
        
        # Create two companies with different rules
        company_a = CompanyFactory(code="COMPANY_A")
        company_b = CompanyFactory(code="COMPANY_B")
        
        # Company A rules - focus on product codes
        TaggingRuleFactory(
            company=company_a,
            rule_config={
                'mappings': {
                    'product_code': {
                        'SHARED_001': 'COMPANY_A_PRODUCT_TAG'
                    }
                }
            }
        )
        
        # Company B rules - focus on source
        TaggingRuleFactory(
            company=company_b,
            rule_config={
                'mappings': {
                    'source': {
                        'online': 'COMPANY_B_ONLINE_TAG'
                    }
                }
            }
        )
        
        # Tag with both companies
        service = AutoTagService()
        
        result_a = service.tag_single_transaction(
            shared_transaction.id, 
            company_a.code
        )
        result_b = service.tag_single_transaction(
            shared_transaction.id,
            company_b.code
        )
        
        self.assertEqual(result_a, 'COMPANY_A_PRODUCT_TAG')
        self.assertEqual(result_b, 'COMPANY_B_ONLINE_TAG')
        
        # Verify separate tags exist
        tags = TransactionTag.objects.filter(transaction=shared_transaction)
        self.assertEqual(tags.count(), 2)
        
        tag_a = tags.get(company=company_a)
        tag_b = tags.get(company=company_b)
        
        self.assertEqual(tag_a.tag_code, 'COMPANY_A_PRODUCT_TAG')
        self.assertEqual(tag_b.tag_code, 'COMPANY_B_ONLINE_TAG')
    
    def test_large_scale_performance(self):
        """Test performance with large number of transactions and rules"""
        # Create many transactions
        num_transactions = 100
        transactions = []
        
        for i in range(num_transactions):
            txn = TransactionFactory(
                product_code=f"PERF_TEST_{i:03d}",
                produce_rate=Decimal(str(100 + i)),
                source=['online', 'pos', 'mobile'][i % 3]
            )
            ExternalDataFactory(
                transaction=txn,
                metadata={
                    'customer_id': f'CUST_{i:05d}',
                    'amount': 100 + i,
                    'region': ['north', 'south', 'east', 'west'][i % 4]
                }
            )
            transactions.append(txn)
        
        # Create many rules
        num_rules = 20
        for i in range(num_rules):
            if i % 3 == 0:
                # Simple rules
                TaggingRuleFactory(
                    company=self.company,
                    name=f"Simple Rule {i}",
                    rule_type='simple',
                    priority=100 + i,
                    rule_config={
                        'mappings': {
                            'source': {
                                ['online', 'pos', 'mobile'][i % 3]: f'SIMPLE_TAG_{i}'
                            }
                        }
                    }
                )
            elif i % 3 == 1:
                # Conditional rules
                TaggingRuleFactory(
                    company=self.company,
                    name=f"Conditional Rule {i}",
                    rule_type='conditional',
                    priority=100 + i,
                    rule_config={
                        'conditions': [
                            {
                                'field': 'metadata.amount',
                                'operator': 'greater_than',
                                'value': 100 + (i * 5),
                                'tag': f'CONDITIONAL_TAG_{i}'
                            }
                        ]
                    }
                )
            else:
                # Script rules
                TaggingRuleFactory(
                    company=self.company,
                    name=f"Script Rule {i}",
                    rule_type='script',
                    priority=100 + i,
                    rule_config={
                        'script': f'''def get_tag(transaction, metadata):
    if metadata.get('amount', 0) > {100 + i * 3}:
        return 'SCRIPT_TAG_{i}'
    return None'''
                    }
                )
        
        # Tag all transactions
        transaction_ids = [txn.id for txn in transactions]
        
        import time
        start_time = time.time()
        
        results = self.service.tag_multiple_transactions(
            transaction_ids,
            self.company.code,
            batch_size=50
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Verify results
        self.assertEqual(len(results), num_transactions)
        
        # Check that some transactions were tagged
        tagged_count = sum(1 for tag in results.values() if tag is not None)
        self.assertGreater(tagged_count, 0)
        
        # Performance assertion - should complete in reasonable time
        self.assertLess(execution_time, 30.0, "Large scale tagging took too long")
        
        # Check statistics
        stats = self.service.get_tagging_stats(self.company.code)
        self.assertEqual(stats['total_transactions'], num_transactions)
        self.assertEqual(stats['tagged_transactions'], tagged_count)
    
    def test_error_recovery_and_resilience(self):
        """Test system resilience to various error conditions"""
        # Create transactions
        good_transaction = TransactionFactory(product_code="GOOD_001")
        ExternalDataFactory(
            transaction=good_transaction,
            metadata={'customer_tier': 'gold'}
        )
        
        # Create mix of good and problematic rules
        rules = [
            # Good rule
            TaggingRuleFactory(
                company=self.company,
                name="Good Rule",
                rule_type='simple',
                priority=10,
                rule_config={
                    'mappings': {
                        'product_code': {
                            'GOOD_001': 'GOOD_TAG'
                        }
                    }
                }
            ),
            # Script rule with error
            TaggingRuleFactory(
                company=self.company,
                name="Error Script Rule",
                rule_type='script',
                priority=20,
                rule_config={
                    'script': '''def get_tag(transaction, metadata):
    # This will cause an error
    return undefined_variable + "test"'''
                }
            ),
            # Rule with invalid config
            TaggingRuleFactory(
                company=self.company,
                name="Invalid Config Rule", 
                rule_type='conditional',
                priority=30,
                rule_config={
                    # Missing conditions key
                    'invalid_key': 'invalid_value'
                }
            ),
            # Another good rule
            TaggingRuleFactory(
                company=self.company,
                name="Backup Rule",
                rule_type='simple',
                priority=40,
                rule_config={
                    'mappings': {
                        'product_code': {
                            'GOOD_001': 'BACKUP_TAG'
                        }
                    }
                }
            )
        ]
        
        # Tag the transaction - should succeed despite errors
        result = self.service.tag_single_transaction(
            good_transaction.id,
            self.company.code
        )
        
        # Should get the first good rule's result
        self.assertEqual(result, 'GOOD_TAG')
        
        # Check that processing notes include error information
        tag = TransactionTag.objects.get(
            transaction=good_transaction,
            company=self.company
        )
        
        self.assertIn('Good Rule', tag.processing_notes)
        self.assertIn('failed', tag.processing_notes.lower())
    
    def test_concurrent_tagging_safety(self):
        """Test thread safety of concurrent tagging operations"""
        import threading
        import time
        
        # Create transactions
        transactions = [
            TransactionFactory(product_code=f"CONCURRENT_{i:03d}")
            for i in range(10)
        ]
        
        for txn in transactions:
            ExternalDataFactory(
                transaction=txn,
                metadata={'test_field': 'test_value'}
            )
        
        # Create rule
        TaggingRuleFactory(
            company=self.company,
            rule_config={
                'mappings': {
                    'product_code': {
                        f'CONCURRENT_{i:03d}': f'CONCURRENT_TAG_{i:03d}'
                        for i in range(10)
                    }
                }
            }
        )
        
        results = {}
        errors = []
        
        def tag_transaction(txn):
            try:
                result = self.service.tag_single_transaction(
                    txn.id,
                    self.company.code
                )
                results[txn.id] = result
            except Exception as e:
                errors.append(str(e))
        
        # Create threads to tag transactions concurrently
        threads = []
        for txn in transactions:
            thread = threading.Thread(target=tag_transaction, args=(txn,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify results
        self.assertEqual(len(errors), 0, f"Concurrent errors: {errors}")
        self.assertEqual(len(results), 10)
        
        # Verify all tags were created correctly
        for txn in transactions:
            expected_tag = f'CONCURRENT_TAG_{txn.product_code.split("_")[1]}'
            self.assertEqual(results[txn.id], expected_tag)
            
            # Verify database consistency
            tag = TransactionTag.objects.get(
                transaction=txn,
                company=self.company
            )
            self.assertEqual(tag.tag_code, expected_tag)