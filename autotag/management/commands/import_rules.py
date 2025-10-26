from django.core.management.base import BaseCommand, CommandError
import json
from pathlib import Path
from autotag.utils import import_rules_from_json, generate_sample_rules
from autotag.models import Company


class Command(BaseCommand):
    help = 'Import tagging rules from JSON file'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'file_path',
            type=str,
            help='Path to JSON file containing rules'
        )
        
        parser.add_argument(
            '--create-company',
            action='store_true',
            help='Create company if it does not exist'
        )
        
        parser.add_argument(
            '--generate-sample',
            action='store_true',
            help='Generate a sample rules file instead of importing'
        )
    
    def handle(self, *args, **options):
        file_path = options['file_path']
        create_company = options.get('create_company')
        generate_sample = options.get('generate_sample')
        
        if generate_sample:
            # Generate sample rules file
            sample_rules = {
                'company_code': 'SAMPLE_CO',
                'company_name': 'Sample Company',
                'rules': generate_sample_rules()
            }
            
            try:
                with open(file_path, 'w') as f:
                    json.dump(sample_rules, f, indent=2)
                
                self.stdout.write(
                    self.style.SUCCESS(f"Sample rules file created at: {file_path}")
                )
                
                self.stdout.write("\nSample contains:")
                for rule in sample_rules['rules']:
                    self.stdout.write(f"  - {rule['name']} ({rule['rule_type']})")
                
                return
                
            except Exception as e:
                raise CommandError(f"Error creating sample file: {str(e)}")
        
        # Import rules from file
        if not Path(file_path).exists():
            raise CommandError(f"File not found: {file_path}")
        
        try:
            with open(file_path, 'r') as f:
                json_data = f.read()
        except Exception as e:
            raise CommandError(f"Error reading file: {str(e)}")
        
        # Parse JSON to check company
        try:
            data = json.loads(json_data)
            company_code = data.get('company_code')
            company_name = data.get('company_name', company_code)
        except json.JSONDecodeError as e:
            raise CommandError(f"Invalid JSON: {str(e)}")
        
        if not company_code:
            raise CommandError("JSON must contain 'company_code'")
        
        # Create company if requested
        if create_company:
            company, created = Company.objects.get_or_create(
                code=company_code,
                defaults={
                    'name': company_name,
                    'is_active': True
                }
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created company: {company_name} ({company_code})")
                )
        
        # Import the rules
        self.stdout.write(f"Importing rules for company: {company_code}")
        
        results = import_rules_from_json(json_data)
        
        if 'error' in results:
            raise CommandError(results['error'])
        
        self.stdout.write(
            self.style.SUCCESS(f"Successfully imported {results['imported']} rules")
        )
        
        if results.get('errors'):
            self.stdout.write(self.style.WARNING("\nErrors encountered:"))
            for error in results['errors']:
                self.stdout.write(f"  - {error}")
        
        # Show summary
        from autotag.models import TaggingRule
        
        total_rules = TaggingRule.objects.filter(
            company__code=company_code
        ).count()
        
        active_rules = TaggingRule.objects.filter(
            company__code=company_code,
            is_active=True
        ).count()
        
        self.stdout.write(f"\nCompany '{company_code}' now has:")
        self.stdout.write(f"  Total rules: {total_rules}")
        self.stdout.write(f"  Active rules: {active_rules}")