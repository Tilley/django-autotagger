import json
from typing import Dict, Any, List
from jsonschema import validate, ValidationError


def validate_rule_config(rule_type: str, rule_config: Dict[str, Any]) -> bool:
    """
    Validate rule configuration based on rule type.
    
    Args:
        rule_type: Type of rule (simple, conditional, script, ml)
        rule_config: Rule configuration to validate
        
    Returns:
        bool: True if valid, raises ValueError if invalid
    """
    if rule_type == 'simple':
        if 'mappings' not in rule_config:
            raise ValueError("Simple rules must have 'mappings' field")
        
        if not isinstance(rule_config['mappings'], dict):
            raise ValueError("'mappings' must be a dictionary")
            
    elif rule_type == 'conditional':
        if 'conditions' not in rule_config:
            raise ValueError("Conditional rules must have 'conditions' field")
        
        if not isinstance(rule_config['conditions'], list):
            raise ValueError("'conditions' must be a list")
            
    elif rule_type == 'script':
        if 'script' not in rule_config:
            raise ValueError("Script rules must have 'script' field")
        
        if not isinstance(rule_config['script'], str):
            raise ValueError("'script' must be a string")
        
        # Basic syntax check
        try:
            compile(rule_config['script'], '<string>', 'exec')
        except SyntaxError as e:
            raise ValueError(f"Invalid Python syntax in script: {e}")
            
    elif rule_type == 'ml':
        if 'model_type' not in rule_config:
            raise ValueError("ML rules must have 'model_type' field")
    
    return True


def validate_metadata_against_schema(metadata: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """
    Validate metadata against a JSON schema.
    
    Args:
        metadata: Metadata to validate
        schema: JSON schema to validate against
        
    Returns:
        bool: True if valid
        
    Raises:
        ValidationError: If validation fails
    """
    if not schema:
        return True
        
    try:
        validate(instance=metadata, schema=schema)
        return True
    except ValidationError as e:
        raise ValidationError(f"Metadata validation failed: {e.message}")


def export_rules_to_json(company_code: str) -> str:
    """
    Export all rules for a company to JSON format.
    
    Args:
        company_code: Code of the company
        
    Returns:
        str: JSON string of rules
    """
    from .models import Company, TaggingRule
    
    try:
        company = Company.objects.get(code=company_code)
    except Company.DoesNotExist:
        return json.dumps({"error": "Company not found"})
    
    rules = TaggingRule.objects.filter(company=company)
    
    rules_data = []
    for rule in rules:
        rules_data.append({
            'name': rule.name,
            'rule_type': rule.rule_type,
            'priority': rule.priority,
            'rule_config': rule.rule_config,
            'conditions': rule.conditions,
            'is_active': rule.is_active
        })
    
    return json.dumps({
        'company_code': company_code,
        'company_name': company.name,
        'rules': rules_data
    }, indent=2)


def import_rules_from_json(json_data: str) -> Dict[str, Any]:
    """
    Import rules from JSON format.
    
    Args:
        json_data: JSON string containing rules
        
    Returns:
        Dict with import results
    """
    from .models import Company, TaggingRule
    
    try:
        data = json.loads(json_data)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}
    
    company_code = data.get('company_code')
    if not company_code:
        return {"error": "Missing company_code in JSON"}
    
    try:
        company = Company.objects.get(code=company_code)
    except Company.DoesNotExist:
        return {"error": f"Company with code '{company_code}' not found"}
    
    rules = data.get('rules', [])
    results = {
        'imported': 0,
        'errors': []
    }
    
    for rule_data in rules:
        try:
            # Validate rule config
            validate_rule_config(rule_data['rule_type'], rule_data['rule_config'])
            
            # Create or update rule
            TaggingRule.objects.update_or_create(
                company=company,
                name=rule_data['name'],
                defaults={
                    'rule_type': rule_data['rule_type'],
                    'priority': rule_data.get('priority', 100),
                    'rule_config': rule_data['rule_config'],
                    'conditions': rule_data.get('conditions', {}),
                    'is_active': rule_data.get('is_active', True)
                }
            )
            results['imported'] += 1
            
        except Exception as e:
            results['errors'].append(f"Error importing rule '{rule_data.get('name', 'Unknown')}': {str(e)}")
    
    return results


def generate_sample_rules() -> List[Dict[str, Any]]:
    """
    Generate sample rules for different rule types.
    
    Returns:
        List of sample rule configurations
    """
    return [
        {
            'name': 'Simple Product Mapping',
            'rule_type': 'simple',
            'priority': 100,
            'rule_config': {
                'mappings': {
                    'product_code': {
                        'PROD_A': 'TAG_001',
                        'PROD_B': 'TAG_002',
                        'PROD_C': 'TAG_003'
                    }
                }
            },
            'conditions': {},
            'is_active': True
        },
        {
            'name': 'High Value Online Transactions',
            'rule_type': 'conditional',
            'priority': 50,
            'rule_config': {
                'conditions': [
                    {
                        'conditions': [
                            {'field': 'source', 'operator': 'equals', 'value': 'online'},
                            {'field': 'metadata.amount', 'operator': 'greater_than', 'value': 1000}
                        ],
                        'operator': 'and',
                        'tag': 'HIGH_VALUE_ONLINE'
                    }
                ]
            },
            'conditions': {},
            'is_active': True
        },
        {
            'name': 'Premium Customer Script',
            'rule_type': 'script',
            'priority': 25,
            'rule_config': {
                'script': '''def get_tag(transaction, metadata):
    customer_tier = metadata.get('customer_tier', '')
    if customer_tier == 'gold' and transaction.produce_rate > 100:
        return 'GOLD_PREMIUM'
    elif customer_tier == 'silver' and transaction.produce_rate > 50:
        return 'SILVER_PREMIUM'
    return None'''
            },
            'conditions': {
                'field': 'metadata.customer_tier',
                'operator': 'exists'
            },
            'is_active': True
        }
    ]