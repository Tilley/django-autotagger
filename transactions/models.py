from django.db import models
from django.utils import timezone


class Transaction(models.Model):
    LEDGER_TYPE_CHOICES = [
        ('debit', 'Debit'),
        ('credit', 'Credit'),
    ]
    
    SOURCE_CHOICES = [
        ('online', 'Online'),
        ('pos', 'Point of Sale'),
        ('mobile', 'Mobile App'),
        ('bank', 'Bank Transfer'),
        ('cash', 'Cash'),
    ]
    
    JURISDICTION_CHOICES = [
        ('us', 'United States'),
        ('ca', 'Canada'),
        ('uk', 'United Kingdom'),
        ('eu', 'European Union'),
        ('au', 'Australia'),
    ]
    
    product_code = models.CharField(max_length=50)
    produce_rate = models.DecimalField(max_digits=10, decimal_places=4)
    ledger_type = models.CharField(max_length=10, choices=LEDGER_TYPE_CHOICES)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    jurisdiction = models.CharField(max_length=5, choices=JURISDICTION_CHOICES)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Transaction {self.id} - {self.product_code}"


class ExternalData(models.Model):
    transaction = models.OneToOneField(
        Transaction, 
        on_delete=models.CASCADE, 
        related_name='external_data'
    )
    metadata = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'external_data'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"ExternalData for Transaction {self.transaction.id}"
