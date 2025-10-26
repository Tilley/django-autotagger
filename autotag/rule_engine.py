from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import json
import re
import math
import datetime
import logging
from django.utils import timezone
import celpy


# Configure security logging
security_logger = logging.getLogger('autotag.security')


class BaseRuleProcessor(ABC):
    @abstractmethod
    def process(self, transaction, metadata: Dict[str, Any], rule_config: Dict[str, Any]) -> Optional[str]:
        """
        Process a transaction and return a tag code or None.
        
        Args:
            transaction: Transaction model instance
            metadata: Metadata from ExternalData
            rule_config: Rule configuration from TaggingRule
            
        Returns:
            Optional[str]: Tag code or None if no match
        """
        pass


class SimpleRuleProcessor(BaseRuleProcessor):
    """
    Simple mapping rules based on exact matches or patterns.
    
    Example rule_config:
    {
        "mappings": {
            "product_code": {
                "PROD_A": "TAG_001",
                "PROD_B": "TAG_002"
            },
            "metadata_field": {
                "value1": "TAG_003",
                "value2": "TAG_004"
            }
        }
    }
    """
    
    def process(self, transaction, metadata: Dict[str, Any], rule_config: Dict[str, Any]) -> Optional[str]:
        mappings = rule_config.get('mappings', {})
        
        # Transaction field names that can be mapped
        transaction_fields = [
            'product_code', 'source', 'jurisdiction', 'ledger_type'
        ]
        
        # Check transaction fields first (higher priority)
        for field_name, field_mappings in mappings.items():
            if field_name in transaction_fields:
                transaction_value = getattr(transaction, field_name, None)
                if transaction_value and transaction_value in field_mappings:
                    return field_mappings[transaction_value]
        
        # Check metadata fields
        for field_name, field_mappings in mappings.items():
            if field_name in transaction_fields:
                continue
                
            if field_name in metadata:
                value = metadata[field_name]
                if str(value) in field_mappings:
                    return field_mappings[str(value)]
        
        return None


class ConditionalRuleProcessor(BaseRuleProcessor):
    """
    Conditional logic rules with support for complex conditions.
    
    Example rule_config:
    {
        "conditions": [
            {
                "field": "product_code",
                "operator": "equals",
                "value": "PROD_A",
                "tag": "TAG_001"
            },
            {
                "field": "metadata.amount",
                "operator": "greater_than",
                "value": 1000,
                "tag": "TAG_002"
            },
            {
                "conditions": [
                    {"field": "source", "operator": "equals", "value": "online"},
                    {"field": "metadata.category", "operator": "contains", "value": "premium"}
                ],
                "operator": "and",
                "tag": "TAG_003"
            }
        ]
    }
    """
    
    def process(self, transaction, metadata: Dict[str, Any], rule_config: Dict[str, Any]) -> Optional[str]:
        conditions = rule_config.get('conditions', [])
        
        for condition in conditions:
            if self._evaluate_condition(transaction, metadata, condition):
                return condition.get('tag')
        
        return None
    
    def _evaluate_condition(self, transaction, metadata: Dict[str, Any], condition: Dict[str, Any]) -> bool:
        if 'conditions' in condition:
            # Handle nested conditions
            operator = condition.get('operator', 'and')
            results = [
                self._evaluate_condition(transaction, metadata, sub_condition)
                for sub_condition in condition['conditions']
            ]
            
            if operator == 'and':
                return all(results)
            elif operator == 'or':
                return any(results)
            else:
                return False
        
        # Single condition
        field = condition.get('field')
        operator = condition.get('operator')
        expected_value = condition.get('value')
        
        actual_value = self._get_field_value(transaction, metadata, field)
        
        return self._compare_values(actual_value, operator, expected_value)
    
    def _get_field_value(self, transaction, metadata: Dict[str, Any], field_path: str):
        if field_path.startswith('metadata.'):
            field_name = field_path[9:]  # Remove 'metadata.' prefix
            return metadata.get(field_name)
        else:
            return getattr(transaction, field_path, None)
    
    def _compare_values(self, actual, operator: str, expected) -> bool:
        if operator == 'equals':
            return actual == expected
        elif operator == 'not_equals':
            return actual != expected
        elif operator == 'greater_than':
            try:
                # Try numeric comparison first
                return float(actual) > float(expected)
            except (ValueError, TypeError):
                # Fall back to string comparison
                return str(actual) > str(expected)
        elif operator == 'less_than':
            try:
                # Try numeric comparison first
                return float(actual) < float(expected)
            except (ValueError, TypeError):
                # Fall back to string comparison
                return str(actual) < str(expected)
        elif operator == 'contains':
            return str(expected) in str(actual)
        elif operator == 'regex':
            return bool(re.search(str(expected), str(actual)))
        else:
            return False


class CelRuleProcessor(BaseRuleProcessor):
    """
    CEL (Common Expression Language) processor for safe expression evaluation.
    
    CEL is a non-Turing complete expression language that's safe by design.
    No imports, no file access, no dangerous operations possible.
    
    Example rule_config:
    {
        "expression": "transaction.product_code.startsWith('PREMIUM') && metadata.customer_tier == 'gold' ? 'GOLD_PREMIUM' : 'STANDARD_PREMIUM'",
        "default_tag": "BASIC"
    }
    
    Or with conditions:
    {
        "conditions": [
            {
                "expression": "transaction.product_code.startsWith('PREMIUM')",
                "tag": "PREMIUM_TAG"
            },
            {
                "expression": "double(transaction.produce_rate) > 1000.0",
                "tag": "HIGH_VALUE_TAG"
            }
        ],
        "default_tag": null
    }
    """
    
    def __init__(self):
        # Initialize CEL environment  
        self.env = celpy.Environment()
    
    def process(self, transaction, metadata: Dict[str, Any], rule_config: Dict[str, Any]) -> Optional[str]:
        try:
            # Prepare the evaluation context using celpy's json_to_cel conversion
            context = {
                'transaction': celpy.json_to_cel({
                    'product_code': transaction.product_code,
                    'produce_rate': float(transaction.produce_rate),
                    'ledger_type': transaction.ledger_type,
                    'source': transaction.source,
                    'jurisdiction': transaction.jurisdiction,
                    'created_at': transaction.created_at.isoformat() if hasattr(transaction.created_at, 'isoformat') else str(transaction.created_at),
                }),
                'metadata': celpy.json_to_cel(metadata),
                # Add some utility values
                'now': celpy.json_to_cel(timezone.now().isoformat()),
            }
            
            # Check for single expression mode
            if 'expression' in rule_config:
                return self._evaluate_single_expression(rule_config, context)
            
            # Check for multiple conditions mode
            if 'conditions' in rule_config:
                return self._evaluate_conditions(rule_config, context)
            
            # Legacy support for 'script' key - treat as expression
            if 'script' in rule_config:
                # For backward compatibility, try to extract CEL expression from script
                script_content = rule_config.get('script', '')
                # If it looks like a simple CEL expression, use it
                if script_content and not ('def ' in script_content or 'return' in script_content):
                    legacy_config = {'expression': script_content}
                    return self._evaluate_single_expression(legacy_config, context)
                else:
                    # Log that this is an unsupported Python script
                    security_logger.warning(
                        "Python script detected in legacy rule - CEL expressions required",
                        extra={
                            'script_preview': script_content[:100],
                            'event_type': 'legacy_python_script'
                        }
                    )
                    return None
                
            return None
            
        except Exception as e:
            security_logger.error(
                "CEL expression evaluation error",
                extra={
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'rule_config': str(rule_config)[:200],  # Truncate for logging
                    'event_type': 'cel_evaluation_error'
                }
            )
            return None
    
    def _evaluate_single_expression(self, rule_config: Dict[str, Any], context: Dict[str, Any]) -> Optional[str]:
        """Evaluate a single CEL expression that should return a tag or null"""
        expression = rule_config.get('expression', '')
        default_tag = rule_config.get('default_tag')
        
        if not expression:
            return default_tag
            
        try:
            # Compile and evaluate the CEL expression
            ast = self.env.compile(expression)
            program = self.env.program(ast)
            result = program.evaluate(context)
            
            # Convert CEL result back to Python and return if it's a non-empty string
            if hasattr(result, 'value'):
                result_value = result.value
            else:
                result_value = result
                
            if isinstance(result_value, str) and result_value.strip():
                return result_value
            return default_tag
            
        except Exception as e:
            security_logger.warning(
                "CEL expression evaluation failed",
                extra={
                    'expression': expression,
                    'error': str(e),
                    'event_type': 'cel_expression_error'
                }
            )
            return default_tag
    
    def _evaluate_conditions(self, rule_config: Dict[str, Any], context: Dict[str, Any]) -> Optional[str]:
        """Evaluate multiple CEL conditions and return the first matching tag"""
        conditions = rule_config.get('conditions', [])
        default_tag = rule_config.get('default_tag')
        
        for condition in conditions:
            expression = condition.get('expression', '')
            tag = condition.get('tag')
            
            if not expression or not tag:
                continue
                
            try:
                # Compile and evaluate the CEL expression  
                ast = self.env.compile(expression)
                program = self.env.program(ast)
                result = program.evaluate(context)
                
                # Convert CEL result back to Python
                if hasattr(result, 'value'):
                    result_value = result.value
                else:
                    result_value = result
                
                # If the condition evaluates to true, return the tag
                if result_value:
                    return tag
                    
            except Exception as e:
                security_logger.warning(
                    "CEL condition evaluation failed",
                    extra={
                        'expression': expression,
                        'error': str(e),
                        'event_type': 'cel_condition_error'
                    }
                )
                continue
        
        return default_tag


# Legacy alias for backward compatibility
ScriptRuleProcessor = CelRuleProcessor


class MLRuleProcessor(BaseRuleProcessor):
    """
    Machine learning rule processor placeholder.
    
    Example rule_config:
    {
        "model_type": "classification",
        "model_params": {...},
        "feature_mapping": {...}
    }
    """
    
    def process(self, transaction, metadata: Dict[str, Any], rule_config: Dict[str, Any]) -> Optional[str]:
        # Placeholder for ML implementation
        # In a real implementation, this would:
        # 1. Extract features from transaction and metadata
        # 2. Load the trained model
        # 3. Make predictions
        # 4. Return the predicted tag
        return None


class AutoTagEngine:
    """
    Main engine that orchestrates the tagging process.
    """
    
    PROCESSORS = {
        'simple': SimpleRuleProcessor(),
        'conditional': ConditionalRuleProcessor(),
        'script': CelRuleProcessor(),  # Now uses CEL instead of Python
        'cel': CelRuleProcessor(),     # Direct CEL access
        'ml': MLRuleProcessor(),
    }
    
    def tag_transaction(self, transaction, company) -> Optional[str]:
        """
        Tag a transaction based on company rules.
        
        Args:
            transaction: Transaction instance
            company: Company instance
            
        Returns:
            Optional[str]: Tag code or None
        """
        from .models import TransactionTag
        
        # Get metadata
        metadata = {}
        if hasattr(transaction, 'external_data'):
            metadata = transaction.external_data.metadata
        
        # Get company rules ordered by priority
        rules = company.tagging_rules.filter(is_active=True).order_by('priority')
        
        best_tag = None
        best_confidence = 0.0
        processing_notes = []
        
        for rule in rules:
            processor = self.PROCESSORS.get(rule.rule_type)
            if not processor:
                continue
            
            # Check if rule conditions are met
            if not self._check_rule_conditions(transaction, metadata, rule.conditions):
                continue
            
            try:
                tag_code = processor.process(transaction, metadata, rule.rule_config)
                
                if tag_code:
                    confidence = 1.0  # Default confidence, could be improved
                    
                    if confidence > best_confidence:
                        best_tag = tag_code
                        best_confidence = confidence
                    
                    processing_notes.append(f"Rule '{rule.name}' matched: {tag_code}")
                    
                    # If this is a high-priority rule with high confidence, stop processing
                    if rule.priority < 50 and confidence > 0.9:
                        break
                        
            except Exception as e:
                processing_notes.append(f"Rule '{rule.name}' failed: {str(e)}")
        
        # Create or update the tag
        if best_tag:
            tag, created = TransactionTag.objects.update_or_create(
                transaction=transaction,
                company=company,
                defaults={
                    'tag_code': best_tag,
                    'confidence_score': best_confidence,
                    'processing_notes': '\n'.join(processing_notes),
                    'updated_at': timezone.now()
                }
            )
            return best_tag
        
        return None
    
    def _check_rule_conditions(self, transaction, metadata: Dict[str, Any], conditions: Dict[str, Any]) -> bool:
        """Check if rule-level conditions are met."""
        if not conditions:
            return True
        
        processor = ConditionalRuleProcessor()
        return processor._evaluate_condition(transaction, metadata, conditions)