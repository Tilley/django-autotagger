from typing import List, Optional, Dict, Any
from django.db import transaction
from django.db import models
from .models import Company, TransactionTag, TaggingRule
from .rule_engine import AutoTagEngine
from transactions.models import Transaction


class AutoTagService:
    """
    Service layer for auto-tagging operations.
    """
    
    def __init__(self):
        self.engine = AutoTagEngine()
    
    def tag_single_transaction(self, transaction_id: int, company_code: str) -> Optional[str]:
        """
        Tag a single transaction for a specific company.
        
        Args:
            transaction_id: ID of the transaction to tag
            company_code: Code of the company whose rules to apply
            
        Returns:
            Optional[str]: The assigned tag code or None
        """
        try:
            transaction_obj = Transaction.objects.get(id=transaction_id)
            company = Company.objects.get(code=company_code, is_active=True)
            
            return self.engine.tag_transaction(transaction_obj, company)
        except (Transaction.DoesNotExist, Company.DoesNotExist):
            return None
    
    def tag_multiple_transactions(
        self, 
        transaction_ids: List[int], 
        company_code: str,
        batch_size: int = 100
    ) -> Dict[int, Optional[str]]:
        """
        Tag multiple transactions in batches.
        
        Args:
            transaction_ids: List of transaction IDs to tag
            company_code: Code of the company whose rules to apply
            batch_size: Number of transactions to process at once
            
        Returns:
            Dict mapping transaction ID to assigned tag (or None)
        """
        results = {}
        
        try:
            company = Company.objects.get(code=company_code, is_active=True)
        except Company.DoesNotExist:
            return results
        
        # Process in batches
        for i in range(0, len(transaction_ids), batch_size):
            batch_ids = transaction_ids[i:i + batch_size]
            transactions = Transaction.objects.filter(id__in=batch_ids)
            
            for transaction_obj in transactions:
                tag_code = self.engine.tag_transaction(transaction_obj, company)
                results[transaction_obj.id] = tag_code
        
        return results
    
    def retag_company_transactions(self, company_code: str) -> int:
        """
        Re-tag all transactions for a specific company.
        
        Args:
            company_code: Code of the company
            
        Returns:
            int: Number of transactions processed
        """
        try:
            company = Company.objects.get(code=company_code, is_active=True)
        except Company.DoesNotExist:
            return 0
        
        # Get all transactions that have been tagged by this company
        existing_tags = TransactionTag.objects.filter(company=company)
        transaction_ids = list(existing_tags.values_list('transaction_id', flat=True))
        
        # Process them
        results = self.tag_multiple_transactions(transaction_ids, company_code)
        
        return len(results)
    
    @transaction.atomic
    def create_or_update_rule(
        self,
        company_code: str,
        rule_name: str,
        rule_type: str,
        rule_config: Dict[str, Any],
        priority: int = 100,
        conditions: Optional[Dict[str, Any]] = None,
        is_active: bool = True
    ) -> TaggingRule:
        """
        Create or update a tagging rule.
        
        Args:
            company_code: Code of the company
            rule_name: Name of the rule
            rule_type: Type of rule (simple, conditional, script, ml)
            rule_config: Rule configuration
            priority: Rule priority (lower = higher priority)
            conditions: Optional conditions for rule application
            is_active: Whether the rule is active
            
        Returns:
            TaggingRule: The created or updated rule
        """
        company = Company.objects.get(code=company_code)
        
        rule, created = TaggingRule.objects.update_or_create(
            company=company,
            name=rule_name,
            defaults={
                'rule_type': rule_type,
                'rule_config': rule_config,
                'priority': priority,
                'conditions': conditions or {},
                'is_active': is_active
            }
        )
        
        return rule
    
    def get_tagging_stats(self, company_code: str) -> Dict[str, Any]:
        """
        Get tagging statistics for a company.
        
        Args:
            company_code: Code of the company
            
        Returns:
            Dict with tagging statistics
        """
        try:
            company = Company.objects.get(code=company_code)
        except Company.DoesNotExist:
            return {}
        
        total_tags = TransactionTag.objects.filter(company=company).count()
        tagged_count = TransactionTag.objects.filter(
            company=company,
            tag_code__isnull=False
        ).count()
        
        # Get tag distribution
        tag_distribution = {}
        tags = TransactionTag.objects.filter(
            company=company,
            tag_code__isnull=False
        ).values('tag_code').annotate(
            count=models.Count('tag_code')
        ).order_by('-count')
        
        for tag_data in tags[:10]:  # Top 10 tags
            tag_distribution[tag_data['tag_code']] = tag_data['count']
        
        return {
            'total_transactions': total_tags,
            'tagged_transactions': tagged_count,
            'untagged_transactions': total_tags - tagged_count,
            'tagging_rate': (tagged_count / total_tags * 100) if total_tags > 0 else 0,
            'top_tags': tag_distribution,
            'active_rules': TaggingRule.objects.filter(
                company=company,
                is_active=True
            ).count()
        }