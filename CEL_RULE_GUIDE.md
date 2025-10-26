# 🔒 CEL Rule Guide - Safe Expression Language

The Django Auto-Tagger now uses **CEL (Common Expression Language)** for safe, secure rule evaluation. CEL is a non-Turing complete expression language designed by Google for safe policy evaluation.

## 🛡️ Why CEL?

- **Inherently Safe**: No file access, no imports, no dangerous operations
- **Non-Turing Complete**: No infinite loops possible
- **Type Safe**: Prevents type confusion attacks
- **Sandboxed**: Complete isolation from system resources
- **Fast**: Compiled expressions with excellent performance

## 📖 CEL Syntax Overview

CEL expressions are similar to JSON/JavaScript with some differences:

### Basic Operations
```cel
// String operations
transaction.product_code.startsWith('PREMIUM')
transaction.source.endsWith('_API')
transaction.product_code.contains('GOLD')

// Numeric comparisons
transaction.produce_rate > 1000.0
transaction.produce_rate >= 500.0 && transaction.produce_rate <= 2000.0

// String concatenation
'TAG_' + transaction.product_code

// Conditional expressions (ternary operator)
transaction.produce_rate > 1000.0 ? 'HIGH_VALUE' : 'STANDARD'
```

### Metadata Access
```cel
// Access metadata fields
metadata.customer_tier == 'gold'
metadata.priority == 'urgent'
has(metadata.special_flag) && metadata.special_flag

// Check if fields exist
has(metadata.customer_tier)
```

### Logical Operations
```cel
// AND, OR, NOT
transaction.source == 'online' && metadata.customer_tier == 'gold'
transaction.ledger_type == 'credit' || transaction.ledger_type == 'debit'
!has(metadata.exclude_tagging)
```

### Collections and Lists
```cel
// Check if value is in list
transaction.jurisdiction in ['us', 'uk', 'ca']
transaction.source in ['web', 'mobile', 'api']

// List operations
size(['a', 'b', 'c']) == 3
```

## 🎯 Rule Configuration Examples

### Single Expression Mode
```json
{
  "rule_type": "cel",
  "rule_config": {
    "expression": "transaction.product_code.startsWith('PREMIUM') && metadata.customer_tier == 'gold' ? 'GOLD_PREMIUM' : 'STANDARD_PREMIUM'",
    "default_tag": "BASIC"
  }
}
```

### Multiple Conditions Mode
```json
{
  "rule_type": "cel", 
  "rule_config": {
    "conditions": [
      {
        "expression": "transaction.produce_rate > 5000.0",
        "tag": "ULTRA_HIGH_VALUE"
      },
      {
        "expression": "transaction.produce_rate > 1000.0",
        "tag": "HIGH_VALUE"
      },
      {
        "expression": "transaction.source == 'premium_api'",
        "tag": "PREMIUM_SOURCE"
      }
    ],
    "default_tag": "STANDARD"
  }
}
```

## 🔧 Available Data Context

In CEL expressions, you have access to:

### Transaction Object
```cel
transaction.product_code      // String
transaction.produce_rate      // Number (float)
transaction.ledger_type       // String: 'credit' or 'debit'
transaction.source           // String
transaction.jurisdiction     // String
transaction.created_at       // ISO timestamp string
```

### Metadata Object
```cel
metadata.customer_tier       // Any field from metadata JSON
metadata.priority
metadata.flags
// ... any other metadata fields
```

### Utility Values
```cel
now                         // Current timestamp (ISO string)
```

## 📋 Complex Examples

### Customer Tier-Based Tagging
```cel
has(metadata.customer_tier) && metadata.customer_tier == 'platinum' ? 'PLATINUM_CUSTOMER' :
has(metadata.customer_tier) && metadata.customer_tier == 'gold' ? 'GOLD_CUSTOMER' :
has(metadata.customer_tier) && metadata.customer_tier == 'silver' ? 'SILVER_CUSTOMER' :
'STANDARD_CUSTOMER'
```

### Geographic and Value-Based Rules
```cel
transaction.jurisdiction in ['us', 'ca'] && transaction.produce_rate > 1000.0 ? 'NORTH_AMERICA_HIGH_VALUE' :
transaction.jurisdiction in ['uk', 'de', 'fr'] && transaction.produce_rate > 800.0 ? 'EUROPE_HIGH_VALUE' :
transaction.jurisdiction == 'jp' && transaction.produce_rate > 500.0 ? 'JAPAN_HIGH_VALUE' :
'STANDARD_VALUE'
```

### Multi-Factor Authentication Rules
```cel
transaction.source == 'api' && 
has(metadata.auth_method) && 
metadata.auth_method == 'mfa' && 
has(metadata.risk_score) && 
metadata.risk_score < 0.3 ? 'SECURE_API_TRANSACTION' : 'REVIEW_REQUIRED'
```

### Time-Based Rules (using string operations)
```cel
// Check if transaction was created today (simplified)
transaction.created_at.startsWith(now.substring(0, 10)) ? 'TODAY_TRANSACTION' : 'HISTORICAL_TRANSACTION'
```

## ⚡ Performance Tips

1. **Use Early Returns**: Put most specific conditions first
2. **Avoid Deep Nesting**: Break complex rules into multiple simpler rules
3. **Use `has()` for Optional Fields**: Always check if metadata fields exist
4. **Prefer Simple Comparisons**: `==` is faster than regex operations

## 🔒 Security Benefits

### What CEL Prevents (automatically):
- ❌ File system access
- ❌ Network operations
- ❌ Code execution/eval
- ❌ Module imports
- ❌ Infinite loops
- ❌ Memory exhaustion
- ❌ Attribute manipulation
- ❌ Global variable access

### What CEL Allows (safely):
- ✅ Data access and manipulation
- ✅ String operations
- ✅ Mathematical calculations
- ✅ Logical operations
- ✅ Conditional expressions
- ✅ Collection operations
- ✅ Type-safe comparisons

## 🆚 Migration from Python Scripts

### Old Python Script
```python
def get_tag(transaction, metadata):
    if transaction.product_code.startswith('PREMIUM'):
        if metadata.get('customer_tier') == 'gold':
            return 'GOLD_PREMIUM'
        else:
            return 'STANDARD_PREMIUM'
    return None
```

### New CEL Expression
```cel
transaction.product_code.startsWith('PREMIUM') ? 
  (has(metadata.customer_tier) && metadata.customer_tier == 'gold' ? 'GOLD_PREMIUM' : 'STANDARD_PREMIUM') :
  null
```

## 🧪 Testing CEL Expressions

Use the Django shell to test expressions:

```python
from autotag.rule_engine import CelRuleProcessor
from autotag.tests.factories import TransactionFactory

processor = CelRuleProcessor()
transaction = TransactionFactory(product_code="PREMIUM_001")
metadata = {"customer_tier": "gold"}

rule_config = {
    "expression": "transaction.product_code.startsWith('PREMIUM') ? 'SUCCESS' : 'FAIL'"
}

result = processor.process(transaction, metadata, rule_config)
print(result)  # 'SUCCESS'
```

## 📚 Additional Resources

- [CEL Language Definition](https://github.com/google/cel-spec/blob/master/doc/langdef.md)
- [CEL Python Documentation](https://github.com/cloud-custodian/cel-python)
- [CEL Playground](https://github.com/google/cel-go/tree/master/codelab) (Go-based but same syntax)

---

**The rule engine is now production-ready with enterprise-grade security! 🚀**