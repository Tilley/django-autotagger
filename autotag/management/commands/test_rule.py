from django.core.management.base import BaseCommand, CommandError
import json
from autotag.models import Company, TaggingRule
from autotag.rule_engine import AutoTagEngine
from transactions.models import Transaction


class Command(BaseCommand):
    help = 'Test a specific tagging rule against transactions'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'company_code',
            type=str,
            help='Company code'
        )
        
        parser.add_argument(
            'rule_name',
            type=str,
            help='Name of the rule to test'
        )
        
        parser.add_argument(
            '--transaction-id',
            type=int,
            help='Specific transaction ID to test against'
        )
        
        parser.add_argument(
            '--sample-size',
            type=int,
            default=10,
            help='Number of sample transactions to test (default: 10)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Test without saving results'
        )
    
    def handle(self, *args, **options):
        company_code = options['company_code']
        rule_name = options['rule_name']
        transaction_id = options.get('transaction_id')
        sample_size = options.get('sample_size')
        dry_run = options.get('dry_run')
        
        try:
            company = Company.objects.get(code=company_code)
            rule = TaggingRule.objects.get(company=company, name=rule_name)
        except Company.DoesNotExist:
            raise CommandError(f"Company '{company_code}' not found")
        except TaggingRule.DoesNotExist:
            raise CommandError(f"Rule '{rule_name}' not found for company '{company_code}'")
        
        self.stdout.write(f"\nTesting rule: {rule_name}")
        self.stdout.write(f"Rule type: {rule.rule_type}")
        self.stdout.write(f"Priority: {rule.priority}")
        self.stdout.write(f"Active: {rule.is_active}")
        
        # Show rule configuration
        self.stdout.write("\nRule configuration:")
        self.stdout.write(json.dumps(rule.rule_config, indent=2))
        
        if rule.conditions:
            self.stdout.write("\nRule conditions:")
            self.stdout.write(json.dumps(rule.conditions, indent=2))
        
        # Get the processor
        engine = AutoTagEngine()
        processor = engine.PROCESSORS.get(rule.rule_type)
        
        if not processor:
            raise CommandError(f"No processor found for rule type: {rule.rule_type}")
        
        # Get transactions to test
        if transaction_id:
            transactions = Transaction.objects.filter(id=transaction_id)
            if not transactions.exists():
                raise CommandError(f"Transaction {transaction_id} not found")
        else:
            transactions = Transaction.objects.all()[:sample_size]
        
        self.stdout.write(f"\nTesting against {transactions.count()} transaction(s):")
        self.stdout.write("-" * 60)
        
        matches = 0
        
        for txn in transactions:
            # Get metadata
            metadata = {}
            if hasattr(txn, 'external_data'):
                metadata = txn.external_data.metadata
            
            # Check rule conditions
            conditions_met = engine._check_rule_conditions(txn, metadata, rule.conditions)
            
            if not conditions_met:
                self.stdout.write(
                    f"\nTransaction {txn.id}: Conditions not met"
                )
                continue
            
            # Process the rule
            try:
                result = processor.process(txn, metadata, rule.rule_config)
                
                if result:
                    matches += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"\nTransaction {txn.id}: MATCHED → {result}")
                    )
                    
                    # Show transaction details
                    self.stdout.write(f"  Product: {txn.product_code}")
                    self.stdout.write(f"  Source: {txn.source}")
                    self.stdout.write(f"  Jurisdiction: {txn.jurisdiction}")
                    self.stdout.write(f"  Produce rate: {txn.produce_rate}")
                    
                    if metadata:
                        self.stdout.write("  Metadata:")
                        for key, value in metadata.items():
                            self.stdout.write(f"    {key}: {value}")
                    
                    # Save the tag if not dry run
                    if not dry_run:
                        from autotag.models import TransactionTag
                        tag, created = TransactionTag.objects.update_or_create(
                            transaction=txn,
                            company=company,
                            defaults={
                                'tag_code': result,
                                'confidence_score': 1.0,
                                'processing_notes': f"Tagged by rule '{rule_name}' (test)"
                            }
                        )
                        if created:
                            self.stdout.write("  → Tag saved")
                        else:
                            self.stdout.write("  → Tag updated")
                else:
                    self.stdout.write(f"\nTransaction {txn.id}: No match")
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"\nTransaction {txn.id}: ERROR - {str(e)}")
                )
        
        # Summary
        self.stdout.write("-" * 60)
        self.stdout.write(
            self.style.SUCCESS(f"\nMatches: {matches}/{transactions.count()}")
        )
        
        if dry_run:
            self.stdout.write("\n(Dry run - no changes saved)")