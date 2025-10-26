from django.test import TestCase
import json
from jsonschema import ValidationError
from autotag.utils import (
    validate_rule_config, validate_metadata_against_schema,
    export_rules_to_json, import_rules_from_json, generate_sample_rules
)
from autotag.models import Company, TaggingRule
from autotag.tests.factories import CompanyFactory, TaggingRuleFactory


class TestUtilityFunctions(TestCase):
    """Test utility functions in autotag.utils"""
    
    def setUp(self):
        self.company = CompanyFactory(code="UTILS_TEST_CO")
    
    def test_validate_rule_config_simple_valid(self):
        """Test validation of valid simple rule config"""
        config = {
            'mappings': {
                'product_code': {
                    'PROD_A': 'TAG_A',
                    'PROD_B': 'TAG_B'
                },
                'source': {
                    'online': 'ONLINE_TAG'
                }
            }
        }
        
        result = validate_rule_config('simple', config)
        self.assertTrue(result)
    
    def test_validate_rule_config_simple_missing_mappings(self):
        """Test validation of simple rule config without mappings"""
        config = {}
        
        with self.assertRaises(ValueError) as cm:
            validate_rule_config('simple', config)
        
        self.assertIn('mappings', str(cm.exception))
    
    def test_validate_rule_config_simple_invalid_mappings_type(self):
        """Test validation of simple rule config with invalid mappings type"""
        config = {'mappings': 'not_a_dict'}
        
        with self.assertRaises(ValueError) as cm:
            validate_rule_config('simple', config)
        
        self.assertIn('dictionary', str(cm.exception))
    
    def test_validate_rule_config_conditional_valid(self):
        """Test validation of valid conditional rule config"""
        config = {
            'conditions': [
                {
                    'field': 'product_code',
                    'operator': 'equals',
                    'value': 'PROD_A',
                    'tag': 'TAG_A'
                },
                {
                    'conditions': [
                        {'field': 'source', 'operator': 'equals', 'value': 'online'},
                        {'field': 'amount', 'operator': 'greater_than', 'value': 1000}
                    ],
                    'operator': 'and',
                    'tag': 'COMPLEX_TAG'
                }
            ]
        }
        
        result = validate_rule_config('conditional', config)
        self.assertTrue(result)
    
    def test_validate_rule_config_conditional_missing_conditions(self):
        """Test validation of conditional rule config without conditions"""
        config = {}
        
        with self.assertRaises(ValueError) as cm:
            validate_rule_config('conditional', config)
        
        self.assertIn('conditions', str(cm.exception))
    
    def test_validate_rule_config_conditional_invalid_conditions_type(self):
        """Test validation of conditional rule config with invalid conditions type"""
        config = {'conditions': 'not_a_list'}
        
        with self.assertRaises(ValueError) as cm:
            validate_rule_config('conditional', config)
        
        self.assertIn('list', str(cm.exception))
    
    def test_validate_rule_config_script_valid(self):
        """Test validation of valid script rule config"""
        config = {
            'script': '''def get_tag(transaction, metadata):
    if transaction.product_code == 'PREMIUM':
        return 'PREMIUM_TAG'
    return None'''
        }
        
        result = validate_rule_config('script', config)
        self.assertTrue(result)
    
    def test_validate_rule_config_script_missing_script(self):
        """Test validation of script rule config without script"""
        config = {}
        
        with self.assertRaises(ValueError) as cm:
            validate_rule_config('script', config)
        
        self.assertIn('script', str(cm.exception))
    
    def test_validate_rule_config_script_invalid_script_type(self):
        """Test validation of script rule config with invalid script type"""
        config = {'script': 123}
        
        with self.assertRaises(ValueError) as cm:
            validate_rule_config('script', config)
        
        self.assertIn('string', str(cm.exception))
    
    def test_validate_rule_config_script_syntax_error(self):
        """Test validation of script rule config with syntax error"""
        config = {
            'script': '''def get_tag(transaction, metadata)  # Missing colon
    return 'TAG'
'''
        }
        
        with self.assertRaises(ValueError) as cm:
            validate_rule_config('script', config)
        
        self.assertIn('syntax', str(cm.exception).lower())
    
    def test_validate_rule_config_ml_valid(self):
        """Test validation of valid ML rule config"""
        config = {
            'model_type': 'classification',
            'model_params': {
                'algorithm': 'random_forest',
                'n_estimators': 100
            },
            'feature_mapping': {
                'amount': 'metadata.amount',
                'tier': 'metadata.customer_tier'
            }
        }
        
        result = validate_rule_config('ml', config)
        self.assertTrue(result)
    
    def test_validate_rule_config_ml_missing_model_type(self):
        """Test validation of ML rule config without model_type"""
        config = {}
        
        with self.assertRaises(ValueError) as cm:
            validate_rule_config('ml', config)
        
        self.assertIn('model_type', str(cm.exception))
    
    def test_validate_rule_config_unknown_rule_type(self):
        """Test validation with unknown rule type"""
        config = {'test': 'value'}
        
        # Should not raise exception for unknown types
        result = validate_rule_config('unknown_type', config)
        self.assertTrue(result)
    
    def test_validate_metadata_against_schema_valid(self):
        """Test metadata validation against valid schema"""
        metadata = {
            'customer_id': 'CUST_123',
            'amount': 1500.00,
            'tier': 'gold'
        }
        
        schema = {
            'type': 'object',
            'properties': {
                'customer_id': {'type': 'string'},
                'amount': {'type': 'number'},
                'tier': {'type': 'string', 'enum': ['bronze', 'silver', 'gold']}
            },
            'required': ['customer_id', 'amount']
        }
        
        result = validate_metadata_against_schema(metadata, schema)
        self.assertTrue(result)
    
    def test_validate_metadata_against_schema_invalid(self):
        """Test metadata validation against schema with invalid data"""
        metadata = {
            'customer_id': 123,  # Should be string
            'amount': 'not_a_number',  # Should be number
            'tier': 'platinum'  # Not in enum
        }
        
        schema = {
            'type': 'object',
            'properties': {
                'customer_id': {'type': 'string'},
                'amount': {'type': 'number'},
                'tier': {'type': 'string', 'enum': ['bronze', 'silver', 'gold']}
            },
            'required': ['customer_id', 'amount']
        }
        
        with self.assertRaises(ValidationError):
            validate_metadata_against_schema(metadata, schema)
    
    def test_validate_metadata_against_schema_empty_schema(self):
        """Test metadata validation with empty schema"""
        metadata = {'any': 'data'}
        schema = {}
        
        result = validate_metadata_against_schema(metadata, schema)
        self.assertTrue(result)
    
    def test_export_rules_to_json_success(self):
        """Test successful export of rules to JSON"""
        # Create rules
        rules = [
            TaggingRuleFactory(
                company=self.company,
                name="Export Rule 1",
                rule_type="simple",
                priority=10,
                rule_config={'mappings': {'field1': {'val1': 'tag1'}}},
                conditions={'test': 'condition'},
                is_active=True
            ),
            TaggingRuleFactory(
                company=self.company,
                name="Export Rule 2",
                rule_type="conditional",
                priority=20,
                rule_config={'conditions': [{'field': 'test', 'operator': 'equals', 'value': 'test', 'tag': 'tag2'}]},
                conditions={},
                is_active=False
            )
        ]
        
        json_str = export_rules_to_json(self.company.code)
        data = json.loads(json_str)
        
        self.assertEqual(data['company_code'], self.company.code)
        self.assertEqual(data['company_name'], self.company.name)
        self.assertEqual(len(data['rules']), 2)
        
        # Check first rule
        rule1 = data['rules'][0]
        self.assertEqual(rule1['name'], "Export Rule 1")
        self.assertEqual(rule1['rule_type'], "simple")
        self.assertEqual(rule1['priority'], 10)
        self.assertEqual(rule1['rule_config'], {'mappings': {'field1': {'val1': 'tag1'}}})
        self.assertEqual(rule1['conditions'], {'test': 'condition'})
        self.assertTrue(rule1['is_active'])
        
        # Check second rule
        rule2 = data['rules'][1]
        self.assertEqual(rule2['name'], "Export Rule 2")
        self.assertEqual(rule2['rule_type'], "conditional")
        self.assertEqual(rule2['priority'], 20)
        self.assertFalse(rule2['is_active'])
    
    def test_export_rules_to_json_company_not_found(self):
        """Test export with non-existent company"""
        json_str = export_rules_to_json("NON_EXISTENT")
        data = json.loads(json_str)
        
        self.assertIn('error', data)
        self.assertIn('not found', data['error'])
    
    def test_export_rules_to_json_no_rules(self):
        """Test export when company has no rules"""
        empty_company = CompanyFactory(code="EMPTY_CO")
        
        json_str = export_rules_to_json(empty_company.code)
        data = json.loads(json_str)
        
        self.assertEqual(data['company_code'], empty_company.code)
        self.assertEqual(data['rules'], [])
    
    def test_import_rules_from_json_success(self):
        """Test successful import of rules from JSON"""
        json_data = {
            'company_code': self.company.code,
            'company_name': self.company.name,
            'rules': [
                {
                    'name': 'Imported Rule 1',
                    'rule_type': 'simple',
                    'priority': 15,
                    'rule_config': {'mappings': {'import_field': {'import_val': 'import_tag'}}},
                    'conditions': {},
                    'is_active': True
                },
                {
                    'name': 'Imported Rule 2',
                    'rule_type': 'conditional',
                    'priority': 25,
                    'rule_config': {'conditions': [{'field': 'import_test', 'operator': 'equals', 'value': 'import_value', 'tag': 'import_tag2'}]},
                    'conditions': {'import': 'condition'},
                    'is_active': False
                }
            ]
        }
        
        json_str = json.dumps(json_data)
        result = import_rules_from_json(json_str)
        
        self.assertEqual(result['imported'], 2)
        self.assertEqual(len(result.get('errors', [])), 0)
        
        # Verify rules were created
        imported_rules = TaggingRule.objects.filter(company=self.company)
        self.assertEqual(imported_rules.count(), 2)
        
        rule1 = imported_rules.get(name='Imported Rule 1')
        self.assertEqual(rule1.rule_type, 'simple')
        self.assertEqual(rule1.priority, 15)
        self.assertTrue(rule1.is_active)
        
        rule2 = imported_rules.get(name='Imported Rule 2')
        self.assertEqual(rule2.rule_type, 'conditional')
        self.assertEqual(rule2.priority, 25)
        self.assertFalse(rule2.is_active)
    
    def test_import_rules_from_json_invalid_json(self):
        """Test import with invalid JSON"""
        invalid_json = '{"invalid": json'
        
        result = import_rules_from_json(invalid_json)
        
        self.assertIn('error', result)
        self.assertIn('JSON', result['error'])
    
    def test_import_rules_from_json_missing_company_code(self):
        """Test import with missing company code"""
        json_data = {
            'company_name': 'Test Company',
            'rules': []
        }
        
        json_str = json.dumps(json_data)
        result = import_rules_from_json(json_str)
        
        self.assertIn('error', result)
        self.assertIn('company_code', result['error'])
    
    def test_import_rules_from_json_company_not_found(self):
        """Test import with non-existent company"""
        json_data = {
            'company_code': 'NON_EXISTENT',
            'rules': []
        }
        
        json_str = json.dumps(json_data)
        result = import_rules_from_json(json_str)
        
        self.assertIn('error', result)
        self.assertIn('not found', result['error'])
    
    def test_import_rules_from_json_with_errors(self):
        """Test import with some valid and some invalid rules"""
        json_data = {
            'company_code': self.company.code,
            'rules': [
                {
                    'name': 'Valid Rule',
                    'rule_type': 'simple',
                    'rule_config': {'mappings': {'field': {'val': 'tag'}}}
                },
                {
                    'name': 'Invalid Rule',
                    'rule_type': 'simple',
                    'rule_config': {}  # Missing mappings - will cause validation error
                },
                {
                    'name': 'Another Valid Rule',
                    'rule_type': 'conditional',
                    'rule_config': {'conditions': [{'field': 'test', 'operator': 'equals', 'value': 'val', 'tag': 'tag'}]}
                }
            ]
        }
        
        json_str = json.dumps(json_data)
        result = import_rules_from_json(json_str)
        
        self.assertEqual(result['imported'], 2)  # Only valid rules imported
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('Invalid Rule', result['errors'][0])
    
    def test_import_rules_from_json_update_existing(self):
        """Test import that updates existing rules"""
        # Create existing rule
        existing_rule = TaggingRuleFactory(
            company=self.company,
            name="Existing Rule",
            rule_type="simple",
            priority=100,
            rule_config={'mappings': {'old': {'val': 'old_tag'}}}
        )
        
        json_data = {
            'company_code': self.company.code,
            'rules': [
                {
                    'name': 'Existing Rule',  # Same name - should update
                    'rule_type': 'conditional',  # Different type
                    'priority': 50,  # Different priority
                    'rule_config': {'conditions': [{'field': 'new', 'operator': 'equals', 'value': 'val', 'tag': 'new_tag'}]}
                }
            ]
        }
        
        json_str = json.dumps(json_data)
        result = import_rules_from_json(json_str)
        
        self.assertEqual(result['imported'], 1)
        
        # Verify rule was updated, not duplicated
        rules = TaggingRule.objects.filter(company=self.company)
        self.assertEqual(rules.count(), 1)
        
        updated_rule = rules.first()
        self.assertEqual(updated_rule.id, existing_rule.id)  # Same rule
        self.assertEqual(updated_rule.rule_type, 'conditional')  # Updated
        self.assertEqual(updated_rule.priority, 50)  # Updated
    
    def test_generate_sample_rules(self):
        """Test generation of sample rules"""
        sample_rules = generate_sample_rules()
        
        self.assertIsInstance(sample_rules, list)
        self.assertGreater(len(sample_rules), 0)
        
        # Check that all required fields are present
        required_fields = ['name', 'rule_type', 'priority', 'rule_config', 'conditions', 'is_active']
        
        for rule in sample_rules:
            for field in required_fields:
                self.assertIn(field, rule)
        
        # Check that we have different rule types
        rule_types = {rule['rule_type'] for rule in sample_rules}
        self.assertIn('simple', rule_types)
        self.assertIn('conditional', rule_types)
        self.assertIn('script', rule_types)
    
    def test_generate_sample_rules_valid_configs(self):
        """Test that generated sample rules have valid configurations"""
        sample_rules = generate_sample_rules()
        
        for rule in sample_rules:
            try:
                validate_rule_config(rule['rule_type'], rule['rule_config'])
            except ValueError as e:
                self.fail(f"Sample rule '{rule['name']}' has invalid config: {e}")
    
    def test_export_import_roundtrip(self):
        """Test that export -> import preserves rule data"""
        # Create original rules
        original_rules = [
            TaggingRuleFactory(
                company=self.company,
                name="Roundtrip Rule 1",
                rule_type="simple",
                priority=10,
                rule_config={'mappings': {'field1': {'val1': 'tag1'}}},
                conditions={'test': 'condition'},
                is_active=True
            ),
            TaggingRuleFactory(
                company=self.company,
                name="Roundtrip Rule 2",
                rule_type="script",
                priority=20,
                rule_config={'script': 'def get_tag(t, m): return "test"'},
                conditions={},
                is_active=False
            )
        ]
        
        # Export
        exported_json = export_rules_to_json(self.company.code)
        
        # Clear rules
        TaggingRule.objects.filter(company=self.company).delete()
        
        # Import
        result = import_rules_from_json(exported_json)
        
        self.assertEqual(result['imported'], 2)
        self.assertEqual(len(result.get('errors', [])), 0)
        
        # Verify imported rules match originals
        imported_rules = TaggingRule.objects.filter(company=self.company).order_by('priority')
        
        for i, imported_rule in enumerate(imported_rules):
            original = original_rules[i]
            
            self.assertEqual(imported_rule.name, original.name)
            self.assertEqual(imported_rule.rule_type, original.rule_type)
            self.assertEqual(imported_rule.priority, original.priority)
            self.assertEqual(imported_rule.rule_config, original.rule_config)
            self.assertEqual(imported_rule.conditions, original.conditions)
            self.assertEqual(imported_rule.is_active, original.is_active)