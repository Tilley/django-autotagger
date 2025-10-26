from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from autotag.services import AutoTagService
from transactions.models import Transaction


class Command(BaseCommand):
    help = 'Tag transactions using company-specific rules'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'company_code',
            type=str,
            help='Company code to use for tagging'
        )
        
        parser.add_argument(
            '--transaction-ids',
            nargs='+',
            type=int,
            help='Specific transaction IDs to tag'
        )
        
        parser.add_argument(
            '--all',
            action='store_true',
            help='Tag all transactions for the company'
        )
        
        parser.add_argument(
            '--retag',
            action='store_true',
            help='Re-tag already tagged transactions'
        )
        
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Batch size for processing (default: 100)'
        )
    
    def handle(self, *args, **options):
        company_code = options['company_code']
        transaction_ids = options.get('transaction_ids')
        tag_all = options.get('all')
        retag = options.get('retag')
        batch_size = options.get('batch_size')
        
        service = AutoTagService()
        
        self.stdout.write(f"Starting tagging process for company: {company_code}")
        start_time = timezone.now()
        
        try:
            if retag:
                # Re-tag existing transactions
                count = service.retag_company_transactions(company_code)
                self.stdout.write(
                    self.style.SUCCESS(f"Re-tagged {count} transactions")
                )
                
            elif transaction_ids:
                # Tag specific transactions
                results = service.tag_multiple_transactions(
                    transaction_ids, 
                    company_code,
                    batch_size
                )
                
                success_count = sum(1 for tag in results.values() if tag is not None)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Tagged {success_count}/{len(transaction_ids)} transactions"
                    )
                )
                
                # Show details for specific transactions
                for txn_id, tag in results.items():
                    if tag:
                        self.stdout.write(f"  Transaction {txn_id}: {tag}")
                    else:
                        self.stdout.write(
                            self.style.WARNING(f"  Transaction {txn_id}: No tag assigned")
                        )
                        
            elif tag_all:
                # Tag all untagged transactions
                from autotag.models import Company, TransactionTag
                
                try:
                    company = Company.objects.get(code=company_code, is_active=True)
                except Company.DoesNotExist:
                    raise CommandError(f"Company '{company_code}' not found or inactive")
                
                # Get all transactions that haven't been tagged by this company
                tagged_txn_ids = TransactionTag.objects.filter(
                    company=company
                ).values_list('transaction_id', flat=True)
                
                untagged_txns = Transaction.objects.exclude(
                    id__in=tagged_txn_ids
                )
                
                transaction_ids = list(untagged_txns.values_list('id', flat=True))
                
                if not transaction_ids:
                    self.stdout.write("No untagged transactions found")
                    return
                
                results = service.tag_multiple_transactions(
                    transaction_ids,
                    company_code,
                    batch_size
                )
                
                success_count = sum(1 for tag in results.values() if tag is not None)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Tagged {success_count}/{len(transaction_ids)} transactions"
                    )
                )
                
            else:
                raise CommandError(
                    "Please specify --transaction-ids, --all, or --retag"
                )
            
            # Show statistics
            stats = service.get_tagging_stats(company_code)
            if stats:
                self.stdout.write("\nTagging Statistics:")
                self.stdout.write(f"  Total transactions: {stats['total_transactions']}")
                self.stdout.write(f"  Tagged: {stats['tagged_transactions']}")
                self.stdout.write(f"  Untagged: {stats['untagged_transactions']}")
                self.stdout.write(f"  Tagging rate: {stats['tagging_rate']:.1f}%")
                
                if stats['top_tags']:
                    self.stdout.write("\n  Top tags:")
                    for tag, count in stats['top_tags'].items():
                        self.stdout.write(f"    {tag}: {count}")
            
            elapsed_time = timezone.now() - start_time
            self.stdout.write(
                self.style.SUCCESS(f"\nCompleted in {elapsed_time.total_seconds():.2f} seconds")
            )
            
        except Exception as e:
            raise CommandError(f"Error during tagging: {str(e)}")