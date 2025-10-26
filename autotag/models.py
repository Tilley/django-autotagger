from django.db import models
from django.utils import timezone
from transactions.models import Transaction


class Company(models.Model):
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=50, unique=True)
    metadata_schema = models.JSONField(default=dict, help_text="JSON schema defining expected metadata structure")
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'companies'
        verbose_name_plural = 'companies'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"


class TransactionTag(models.Model):
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='tags'
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    tag_code = models.CharField(max_length=100, blank=True, null=True)
    confidence_score = models.FloatField(default=0.0, help_text="Confidence in the tagging decision (0-1)")
    is_manual_override = models.BooleanField(default=False)
    processing_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'transaction_tags'
        ordering = ['-created_at']
        unique_together = ['transaction', 'company']
    
    def __str__(self):
        return f"Tag for Transaction {self.transaction.id}: {self.tag_code or 'Untagged'}"


class TaggingRule(models.Model):
    RULE_TYPE_CHOICES = [
        ('simple', 'Simple Mapping'),
        ('conditional', 'Conditional Logic'),
        ('script', 'CEL Expression (Legacy)'),  # Now uses CEL for safety
        ('cel', 'CEL Expression'),              # Direct CEL access
        ('ml', 'Machine Learning'),
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='tagging_rules')
    name = models.CharField(max_length=255)
    rule_type = models.CharField(max_length=20, choices=RULE_TYPE_CHOICES)
    priority = models.IntegerField(default=100, help_text="Lower numbers have higher priority")
    
    # Rule configuration stored as JSON
    rule_config = models.JSONField(
        default=dict,
        help_text="Configuration for the rule (conditions, mappings, script code, etc.)"
    )
    
    # Conditions for when this rule should be applied
    conditions = models.JSONField(
        default=dict,
        help_text="Conditions that must be met for this rule to apply"
    )
    
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tagging_rules'
        ordering = ['company', 'priority', 'name']
        unique_together = ['company', 'name']
    
    def __str__(self):
        return f"{self.company.code} - {self.name} ({self.rule_type})"