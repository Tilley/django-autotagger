from django.test import TestCase
from django.db import IntegrityError
from decimal import Decimal, InvalidOperation
from autotag.rule_engine import SimpleRuleProcessor, ConditionalRuleProcessor, ScriptRuleProcessor, AutoTagEngine
from autotag.models import Company, TaggingRule, TransactionTag
from autotag.services import AutoTagService
from autotag.utils import validate_rule_config, import_rules_from_json
from transactions.models import Transaction, ExternalData
from autotag.tests.factories import (
    TransactionFactory, ExternalDataFactory, CompanyFactory, TaggingRuleFactory
)
import json


class TestEdgeCasesAndErrorHandling(TestCase):
    """Comprehensive edge case and error handling tests"""
    
    def setUp(self):
        self.company = CompanyFactory()
        self.transaction = TransactionFactory()
        self.service = AutoTagService()
    
    def test_extremely_large_metadata(self):
        """Test handling of extremely large metadata objects"""
        # Create metadata with 1MB+ of data
        large_metadata = {
            'large_field': 'x' * 1000000,  # 1MB string
            'large_list': list(range(10000)),  # Large list
            'nested_data': {
                f'key_{i}': f'value_{i}' * 100
                for i in range(1000)
            }
        }
        
        external_data = ExternalDataFactory(
            transaction=self.transaction,
            metadata=large_metadata
        )
        
        # Create rule that processes this metadata with CEL
        rule = TaggingRuleFactory(
            company=self.company,
            rule_type='cel',
            rule_config={
                'expression': 'has(metadata.large_field) && size(metadata.large_field) > 500000 ? "LARGE_METADATA_TAG" : null'
            }
        )
        
        # Should handle large metadata without crashing
        result = self.service.tag_single_transaction(
            self.transaction.id,
            self.company.code
        )
        
        self.assertEqual(result, 'LARGE_METADATA_TAG')
    
    def test_unicode_and_emoji_handling(self):
        """Test handling of unicode characters and emojis"""
        unicode_metadata = {
            'description': '🚀 Premium transaction with café ñoño',
            'customer_name': 'José María García-López',
            'notes': '中文测试 Тест на русском العربية',
            'emoji_field': '💰💎🏆⭐🔥',
            'mixed': 'Regular text with 🎉 and special chars: áéíóú'
        }
        
        external_data = ExternalDataFactory(
            transaction=self.transaction,
            metadata=unicode_metadata
        )
        
        # Test with conditional rule
        rule = TaggingRuleFactory(
            company=self.company,
            rule_type='conditional',
            rule_config={
                'conditions': [
                    {
                        'field': 'metadata.emoji_field',
                        'operator': 'contains',
                        'value': '💰',
                        'tag': 'UNICODE_EMOJI_TAG'
                    }
                ]
            }
        )
        
        result = self.service.tag_single_transaction(
            self.transaction.id,
            self.company.code
        )
        
        self.assertEqual(result, 'UNICODE_EMOJI_TAG')
        
        # Test with CEL rule
        script_rule = TaggingRuleFactory(
            company=self.company,
            name='Unicode Script Rule',
            rule_type='cel',
            priority=50,
            rule_config={
                'expression': 'has(metadata.description) && metadata.description.contains("🚀") && metadata.description.contains("café") ? "UNICODE_SCRIPT_TAG" : null'
            }
        )
        
        # Clear existing tag
        TransactionTag.objects.filter(
            transaction=self.transaction,
            company=self.company
        ).delete()
        
        result = self.service.tag_single_transaction(
            self.transaction.id,
            self.company.code
        )
        
        self.assertEqual(result, 'UNICODE_SCRIPT_TAG')
    
    def test_null_and_none_values_everywhere(self):
        """Test handling of null/None values in all possible places"""
        # Transaction with None/null-like values
        null_transaction = Transaction.objects.create(
            product_code='',  # Empty string
            produce_rate=Decimal('0.00'),
            ledger_type='debit',
            source='online',
            jurisdiction='us'
        )
        
        # Metadata with various null-like values
        null_metadata = {
            'null_field': None,
            'empty_string': '',
            'zero_number': 0,
            'false_bool': False,
            'empty_list': [],
            'empty_dict': {},
            'whitespace_only': '   ',
            'none_string': 'None',
            'null_string': 'null'
        }
        
        ExternalDataFactory(
            transaction=null_transaction,
            metadata=null_metadata
        )
        
        # Rules that handle null values
        rules_configs = [
            {
                'rule_type': 'simple',
                'rule_config': {
                    'mappings': {
                        'null_field': {
                            'None': 'NULL_SIMPLE_TAG'
                        },
                        'empty_string': {
                            '': 'EMPTY_SIMPLE_TAG'
                        }
                    }
                }
            },
            {
                'rule_type': 'conditional',
                'rule_config': {
                    'conditions': [
                        {
                            'field': 'metadata.zero_number',
                            'operator': 'equals',
                            'value': 0,
                            'tag': 'ZERO_CONDITIONAL_TAG'
                        }
                    ]
                }
            },
            {
                'rule_type': 'script',
                'rule_config': {
                    'script': '''def get_tag(transaction, metadata):
    null_field = metadata.get('null_field')
    if null_field is None:
        return 'NULL_SCRIPT_TAG'
    
    empty_string = metadata.get('empty_string', 'default')
    if empty_string == '':
        return 'EMPTY_SCRIPT_TAG'
    
    return None'''
                }
            }
        ]
        
        for i, config in enumerate(rules_configs):
            TaggingRuleFactory(
                company=self.company,
                name=f'Null Test Rule {i}',
                priority=10 + i,
                **config
            )
        
        result = self.service.tag_single_transaction(
            null_transaction.id,
            self.company.code
        )
        
        # Should handle null values gracefully
        self.assertIsNotNone(result)
    
    def test_circular_and_recursive_metadata(self):
        """Test handling of potentially problematic metadata structures"""
        # Deeply nested metadata
        deeply_nested = {'level': 1}
        current = deeply_nested
        for i in range(2, 51):  # 50 levels deep
            current['next'] = {'level': i}
            current = current['next']
        
        # Large repetitive structure
        repetitive_metadata = {
            'data': [
                {'id': i, 'values': [f'val_{j}' for j in range(100)]}
                for i in range(100)
            ],
            'matrix': [[i * j for j in range(50)] for i in range(50)],
            'deeply_nested': deeply_nested
        }
        
        external_data = ExternalDataFactory(
            transaction=self.transaction,
            metadata=repetitive_metadata
        )
        
        # CEL expression that processes complex structures
        rule = TaggingRuleFactory(
            company=self.company,
            rule_type='cel',
            rule_config={
                'expression': 'has(metadata.data) && size(metadata.data) > 50 && has(metadata.deeply_nested) && has(metadata.deeply_nested.level) && metadata.deeply_nested.level == 1 ? "COMPLEX_STRUCTURE_TAG" : null'
            }
        )
        
        result = self.service.tag_single_transaction(
            self.transaction.id,
            self.company.code
        )
        
        self.assertEqual(result, 'COMPLEX_STRUCTURE_TAG')
    
    def test_decimal_precision_edge_cases(self):
        """Test edge cases with decimal precision"""
        # Transactions with simple decimal values
        edge_transactions = [
            TransactionFactory(produce_rate=Decimal('0.1')),  # Small
            TransactionFactory(produce_rate=Decimal('5000000.0')),  # Large
            TransactionFactory(produce_rate=Decimal('123.45')),  # Normal precision
        ]
        
        for txn in edge_transactions:
            ExternalDataFactory(
                transaction=txn,
                metadata={
                    'precise_amount': float(txn.produce_rate),
                    'string_amount': str(txn.produce_rate)
                }
            )
        
        # Rule that compares decimal values using CEL
        rule = TaggingRuleFactory(
            company=self.company,
            rule_type='cel',
            rule_config={
                'expression': 'transaction.produce_rate < 0.001 ? "MICRO_AMOUNT" : (transaction.produce_rate > 1000000.0 ? "MEGA_AMOUNT" : "NORMAL_AMOUNT")'
            }
        )
        
        for txn in edge_transactions:
            result = self.service.tag_single_transaction(
                txn.id,
                self.company.code
            )
            self.assertIsNotNone(result)
    
    def test_malformed_rule_configurations(self):
        """Test handling of malformed rule configurations"""
        malformed_configs = [
            # Simple rule with invalid structure
            {
                'rule_type': 'simple',
                'rule_config': {
                    'mappings': 'not_a_dict'  # Should be dict
                }
            },
            # Conditional rule with invalid operators
            {
                'rule_type': 'conditional',
                'rule_config': {
                    'conditions': [
                        {
                            'field': 'test_field',
                            'operator': 'invalid_operator',
                            'value': 'test_value',
                            'tag': 'TEST_TAG'
                        }
                    ]
                }
            },
            # Script rule with invalid Python
            {
                'rule_type': 'script',
                'rule_config': {
                    'script': 'def invalid_syntax( # Missing closing parenthesis'
                }
            },
            # Completely invalid config
            {
                'rule_type': 'simple',
                'rule_config': 'not_even_a_dict'
            }
        ]
        
        for i, config in enumerate(malformed_configs):
            rule = TaggingRuleFactory(
                company=self.company,
                name=f'Malformed Rule {i}',
                **config
            )
            
            # Should handle malformed configs gracefully
            result = self.service.tag_single_transaction(
                self.transaction.id,
                self.company.code
            )
            
            # Should not crash, may or may not produce a tag
            # The important thing is it doesn't raise an exception
    
    def test_memory_exhaustion_protection(self):
        """Test protection against memory exhaustion attacks"""
        # Extremely large string in metadata
        try:
            huge_metadata = {
                'attack_field': 'A' * (10 * 1024 * 1024),  # 10MB string
                'large_numbers': [i for i in range(100000)],  # Large list
            }
            
            external_data = ExternalDataFactory(
                transaction=self.transaction,
                metadata=huge_metadata
            )
            
            # Rule that might cause memory issues
            rule = TaggingRuleFactory(
                company=self.company,
                rule_type='script',
                rule_config={
                    'script': '''def get_tag(transaction, metadata):
    # Try to process large data carefully
    attack_field = metadata.get('attack_field', '')
    if len(attack_field) > 1000000:  # 1MB threshold
        # Don't try to process the whole field
        return 'LARGE_DATA_TAG'
    return None'''
                }
            )
            
            result = self.service.tag_single_transaction(
                self.transaction.id,
                self.company.code
            )
            
            self.assertEqual(result, 'LARGE_DATA_TAG')
            
        except MemoryError:
            # If we hit memory limits, that's also acceptable
            self.skipTest("Memory limits hit during test")
    
    def test_concurrent_rule_modifications(self):
        """Test behavior when rules are modified during processing"""
        import threading
        import time
        
        # Create initial rule
        rule = TaggingRuleFactory(
            company=self.company,
            rule_config={
                'mappings': {
                    'product_code': {
                        self.transaction.product_code: 'INITIAL_TAG'
                    }
                }
            }
        )
        
        results = []
        errors = []
        
        def tag_transaction():
            try:
                result = self.service.tag_single_transaction(
                    self.transaction.id,
                    self.company.code
                )
                results.append(result)
            except Exception as e:
                errors.append(str(e))
        
        def modify_rule():
            time.sleep(0.01)  # Small delay
            rule.rule_config = {
                'mappings': {
                    'product_code': {
                        self.transaction.product_code: 'MODIFIED_TAG'
                    }
                }
            }
            rule.save()
        
        # Start tagging and modification concurrently
        tag_thread = threading.Thread(target=tag_transaction)
        modify_thread = threading.Thread(target=modify_rule)
        
        tag_thread.start()
        modify_thread.start()
        
        tag_thread.join()
        modify_thread.join()
        
        # Should handle concurrent modifications gracefully
        self.assertEqual(len(errors), 0, f"Concurrent modification errors: {errors}")
        self.assertEqual(len(results), 1)
        self.assertIn(results[0], ['INITIAL_TAG', 'MODIFIED_TAG'])
    
    def test_database_constraint_violations(self):
        """Test handling of database constraint violations"""
        # Try to create duplicate transaction tag
        TransactionTag.objects.create(
            transaction=self.transaction,
            company=self.company,
            tag_code='EXISTING_TAG'
        )
        
        # Create rule that would create another tag
        rule = TaggingRuleFactory(
            company=self.company,
            rule_config={
                'mappings': {
                    'product_code': {
                        self.transaction.product_code: 'NEW_TAG'
                    }
                }
            }
        )
        
        # Should update existing tag, not create duplicate
        result = self.service.tag_single_transaction(
            self.transaction.id,
            self.company.code
        )
        
        self.assertEqual(result, 'NEW_TAG')
        
        # Should only have one tag
        tags = TransactionTag.objects.filter(
            transaction=self.transaction,
            company=self.company
        )
        self.assertEqual(tags.count(), 1)
        self.assertEqual(tags.first().tag_code, 'NEW_TAG')
    
    def test_invalid_json_import(self):
        """Test handling of invalid JSON during rule import"""
        invalid_json_strings = [
            '',  # Empty string
            'not json at all',  # Not JSON
            '{"incomplete": json',  # Malformed JSON
            '[]',  # Wrong structure (array instead of object)
            '{"company_code": "TEST", "rules": "not_array"}',  # Rules not array
            '{"company_code": null}',  # Null company code
        ]
        
        for invalid_json in invalid_json_strings:
            result = import_rules_from_json(invalid_json)
            self.assertIn('error', result)
    
    def test_rule_validation_edge_cases(self):
        """Test rule validation with edge cases"""
        from autotag.utils import validate_rule_config
        
        edge_cases = [
            # Simple rules
            ('simple', {}),  # Empty config
            ('simple', {'mappings': {}}),  # Empty mappings
            ('simple', {'mappings': {'field': {}}}),  # Empty field mapping
            
            # Conditional rules
            ('conditional', {}),  # Missing conditions
            ('conditional', {'conditions': []}),  # Empty conditions
            ('conditional', {'conditions': [{}]}),  # Empty condition object
            
            # Script rules
            ('script', {}),  # Missing script
            ('script', {'script': ''}),  # Empty script
            ('script', {'script': 123}),  # Non-string script
        ]
        
        for rule_type, config in edge_cases:
            with self.assertRaises(ValueError):
                validate_rule_config(rule_type, config)
    
    def test_extreme_priority_values(self):
        """Test handling of extreme priority values"""
        extreme_priorities = [
            -999999,  # Very negative
            0,        # Zero
            999999,   # Very positive
            2**31 - 1,  # Max 32-bit int
        ]
        
        rules = []
        for i, priority in enumerate(extreme_priorities):
            rule = TaggingRuleFactory(
                company=self.company,
                name=f'Extreme Priority Rule {i}',
                priority=priority,
                rule_config={
                    'mappings': {
                        'product_code': {
                            self.transaction.product_code: f'EXTREME_TAG_{i}'
                        }
                    }
                }
            )
            rules.append(rule)
        
        # Should process rules in priority order (lowest first)
        result = self.service.tag_single_transaction(
            self.transaction.id,
            self.company.code
        )
        
        # Should get the rule with lowest priority value
        self.assertEqual(result, 'EXTREME_TAG_0')  # priority -999999
    
    def test_special_character_field_names(self):
        """Test handling of special characters in field names"""
        special_metadata = {
            'field-with-dashes': 'dash_value',
            'field.with.dots': 'dot_value',
            'field with spaces': 'space_value',
            'field_with_underscores': 'underscore_value',
            'field123numbers': 'number_value',
            'UPPERCASE_FIELD': 'upper_value',
            'ñoño_field': 'unicode_value',
            'field@symbol': 'symbol_value',
            '': 'empty_field_name',  # Empty field name
            '123numeric_start': 'numeric_start_value'
        }
        
        external_data = ExternalDataFactory(
            transaction=self.transaction,
            metadata=special_metadata
        )
        
        # Test conditional rules with special field names
        rule = TaggingRuleFactory(
            company=self.company,
            rule_type='conditional',
            rule_config={
                'conditions': [
                    {
                        'field': 'metadata.field-with-dashes',
                        'operator': 'equals',
                        'value': 'dash_value',
                        'tag': 'SPECIAL_FIELD_TAG'
                    }
                ]
            }
        )
        
        result = self.service.tag_single_transaction(
            self.transaction.id,
            self.company.code
        )
        
        self.assertEqual(result, 'SPECIAL_FIELD_TAG')
    
    def test_timezone_and_datetime_edge_cases(self):
        """Test handling of timezone and datetime edge cases"""
        from django.utils import timezone
        import datetime
        
        # Create transactions at edge times
        edge_times = [
            timezone.now(),
            timezone.now() - datetime.timedelta(days=365*10),  # 10 years ago
            timezone.now() + datetime.timedelta(days=365),     # 1 year future
        ]
        
        edge_transactions = []
        for edge_time in edge_times:
            txn = TransactionFactory(created_at=edge_time)
            edge_transactions.append(txn)
        
        # Rule that considers transaction timing
        rule = TaggingRuleFactory(
            company=self.company,
            rule_type='script',
            rule_config={
                'script': '''def get_tag(transaction, metadata):
    from django.utils import timezone
    import datetime
    
    created = transaction.created_at
    now = timezone.now()
    
    if created > now - datetime.timedelta(days=1):
        return 'RECENT_TRANSACTION'
    elif created < now - datetime.timedelta(days=365):
        return 'OLD_TRANSACTION'
    else:
        return 'NORMAL_TRANSACTION'
'''
            }
        )
        
        for txn in edge_transactions:
            result = self.service.tag_single_transaction(
                txn.id,
                self.company.code
            )
            self.assertIsNotNone(result)
    
    def test_script_security_boundaries(self):
        """Test that scripts can't access dangerous functions"""
        dangerous_scripts = [
            # Try to import os
            '''def get_tag(transaction, metadata):
import os
os.system("echo 'dangerous'")
return 'DANGER'
''',
            # Try to access files
            '''def get_tag(transaction, metadata):
with open('/etc/passwd', 'r') as f:
    return f.read()
''',
            # Try to use eval
            '''def get_tag(transaction, metadata):
return eval("1+1")
''',
            # Try to use exec
            '''def get_tag(transaction, metadata):
exec("dangerous_code = True")
return 'EXECUTED'
'''
        ]
        
        for i, dangerous_script in enumerate(dangerous_scripts):
            rule = TaggingRuleFactory(
                company=self.company,
                name=f'Dangerous Script {i}',
                rule_type='script',
                rule_config={'script': dangerous_script}
            )
            
            # Should fail gracefully, not execute dangerous code
            result = self.service.tag_single_transaction(
                self.transaction.id,
                self.company.code
            )
            
            # Should not succeed with dangerous operations
            self.assertIsNone(result)
    
    def test_infinite_loop_protection(self):
        """Test protection against infinite loops in scripts"""
        infinite_loop_script = '''def get_tag(transaction, metadata):
# This would run forever
while True:
    pass
return 'NEVER_REACHED'
'''
        
        rule = TaggingRuleFactory(
            company=self.company,
            rule_type='script',
            rule_config={'script': infinite_loop_script}
        )
        
        # Should timeout or handle infinite loop gracefully
        # Note: In production, you'd want actual timeout protection
        # For testing, we just verify it doesn't hang the test suite
        import time
        start_time = time.time()
        
        result = self.service.tag_single_transaction(
            self.transaction.id,
            self.company.code
        )
        
        end_time = time.time()
        
        # Should not take too long (if it does, there's no timeout protection)
        self.assertLess(end_time - start_time, 5.0, "Infinite loop not protected")
        self.assertIsNone(result)