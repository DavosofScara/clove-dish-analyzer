"""Lightspeed CSV schema detection and mapping"""
import re
from typing import Dict, List, Optional, Set
import unicodedata


class LightspeedMapper:
    """Detect and map Lightspeed CSV exports to canonical fields"""

    # Lightspeed Transactions Report signature headers
    TRANSACTIONS_HEADERS = {
        "Identifier", "PeriodId", "YearId", "Device_Name", "Passive_Device",
        "Date", "Mode", "Account", "AccountName", "Staff", "Reference", "Type",
        "Qty", "UnitPrice", "FinalPrice", "Discount", "Loss", "Comp", "Charge",
        "SKU", "Item", "Group", "StatGroup", "TaxName", "TaxRate", "PreTax",
        "TaxAmount", "Profile"
    }

    # Lightspeed Product Report signature headers (EN)
    PRODUCT_HEADERS_EN = {
        "SKU", "Total Montant", "Total Quantité", "Total Nb Transactions",
        "Nombre d'articles inclus", "Nombre d'articles gratuits",
        "Rabais Montant", "Rabais Quantité", "Rabais Nb Transactions",
        "Offert Montant", "Offert Quantité", "Offert Nb Transactions",
        "Perte Montant", "Perte Quantité", "Perte Nb Transactions",
        "Retour Montant", "Retour Quantité", "Retour Nb Transactions",
        "Transaction Montant", "Transaction Quantité", "Nb Transactions",
        "Marge", "Coûts"
    }

    # Product Report headers (FR variants - normalize accents)
    PRODUCT_HEADERS_FR = {
        "SKU", "Total Montant", "Total Quantite", "Total Nb Transactions",
        "Nombre d'articles inclus", "Nombre d'articles gratuits",
        "Rabais Montant", "Rabais Quantite", "Rabais Nb Transactions",
        "Offert Montant", "Offert Quantite", "Offert Nb Transactions",
        "Perte Montant", "Perte Quantite", "Perte Nb Transactions",
        "Retour Montant", "Retour Quantite", "Retour Nb Transactions",
        "Transaction Montant", "Transaction Quantite", "Nb Transactions",
        "Marge", "Couts"
    }

    @staticmethod
    def normalize_header(header: str) -> str:
        """Normalize header: strip quotes, BOM, whitespace, normalize unicode"""
        # Remove BOM if present
        if header.startswith('\ufeff'):
            header = header[1:]

        # Strip quotes and whitespace
        header = header.strip().strip('"').strip("'")

        # Normalize unicode (NFD -> NFC) to handle accents consistently
        header = unicodedata.normalize('NFD', header)
        header = ''.join(c for c in header if unicodedata.category(c) != 'Mn')

        return header

    @staticmethod
    def normalize_headers(headers: List[str]) -> List[str]:
        """Normalize a list of headers"""
        return [LightspeedMapper.normalize_header(h) for h in headers]

    @classmethod
    def detect_lightspeed_type(cls, headers: List[str]) -> Optional[str]:
        """
        Detect if CSV is a Lightspeed export and return type

        Returns:
        - "transactions" if Transactions Report
        - "products" if Product Report
        - None if not Lightspeed
        """
        normalized = cls.normalize_headers(headers)
        header_set = set(normalized)

        # Check for Transactions Report signature
        # Must have Date, Qty, Item, SKU (core fields)
        transactions_core = {"Date", "Qty", "Item", "SKU"}
        if transactions_core.issubset(header_set):
            # Check if at least 5+ known headers match
            matches = len(cls.TRANSACTIONS_HEADERS.intersection(header_set))
            if matches >= 5:
                return "transactions"

        # Check for Product Report signature
        # Must have SKU and at least one of the French total fields
        product_core = {"SKU"}
        product_signature = {"Total Montant", "Total Quantité", "Total Quantite", "Marge"}

        if product_core.issubset(header_set):
            # Check if signature fields match
            matches_en = len(cls.PRODUCT_HEADERS_EN.intersection(header_set))
            matches_fr = len(cls.PRODUCT_HEADERS_FR.intersection(header_set))
            if matches_en >= 3 or matches_fr >= 3:
                return "products"

        return None

    @classmethod
    def map_transactions_headers(cls, headers: List[str]) -> Dict[str, str]:
        """
        Map Lightspeed Transactions Report headers to canonical fields

        Returns mapping: canonical_field -> original_header_name
        """
        normalized = cls.normalize_headers(headers)
        header_map = {cls.normalize_header(h): h for h in headers}
        mapping = {}

        # Core mappings (case-insensitive)
        field_mappings = {
            "date": ["Date"],
            "sku": ["SKU"],
            "item_name": ["Item"],
            "group": ["Group"],
            "account_name": ["AccountName"],
            "staff": ["Staff"],
            "qty": ["Qty"],
            "unit_price": ["UnitPrice"],
            "final_price": ["FinalPrice"],
            "discount_amount": ["Discount"],
            "loss_amount": ["Loss"],
            "comp_amount": ["Comp"],
            "charge_amount": ["Charge"],
            "pretax_amount": ["PreTax"],
            "tax_amount": ["TaxAmount"],
            "tax_rate": ["TaxRate"],
            "account": ["Account"],
            "mode": ["Mode"],
            "reference": ["Reference"],
            "tax_name": ["TaxName"],
            "stat_group": ["StatGroup"],
            "profile": ["Profile"],
        }

        for canonical_field, possible_headers in field_mappings.items():
            for possible in possible_headers:
                # Case-insensitive match
                normalized_possible = cls.normalize_header(possible)
                for norm_header in normalized:
                    if norm_header.lower() == normalized_possible.lower():
                        mapping[canonical_field] = header_map[norm_header]
                        break
                if canonical_field in mapping:
                    break

        return mapping

    @classmethod
    def map_products_headers(cls, headers: List[str]) -> Dict[str, str]:
        """
        Map Lightspeed Product Report headers to canonical fields

        Returns mapping: canonical_field -> original_header_name
        """
        normalized = cls.normalize_headers(headers)
        header_map = {cls.normalize_header(h): h for h in headers}
        mapping = {}

        # Core mappings for Product Report
        field_mappings = {
            "sku": ["SKU"],
            "total_revenue": ["Total Montant"],
            "total_quantity": ["Total Quantité", "Total Quantite"],
            "total_transactions": ["Total Nb Transactions"],
            "discount_amount": ["Rabais Montant"],
            "discount_quantity": ["Rabais Quantité", "Rabais Quantite"],
            "loss_amount": ["Perte Montant"],
            "loss_quantity": ["Perte Quantité", "Perte Quantite"],
            "return_amount": ["Retour Montant"],
            "return_quantity": ["Retour Quantité", "Retour Quantite"],
            "transaction_amount": ["Transaction Montant"],
            "transaction_quantity": ["Transaction Quantité", "Transaction Quantite"],
            "margin": ["Marge"],
            "costs": ["Coûts", "Couts"],
        }

        for canonical_field, possible_headers in field_mappings.items():
            for possible in possible_headers:
                normalized_possible = cls.normalize_header(possible)
                for norm_header in normalized:
                    if norm_header.lower() == normalized_possible.lower():
                        mapping[canonical_field] = header_map[norm_header]
                        break
                if canonical_field in mapping:
                    break

        return mapping

    @staticmethod
    def normalize_number(value: str) -> float:
        """
        Normalize number formats:
        - Remove currency symbols
        - Convert comma decimals to dots
        - Handle negative indicators
        """
        if not value or value == "":
            return 0.0

        # Convert to string and strip whitespace
        value_str = str(value).strip()

        # Remove currency symbols
        value_str = re.sub(r'[€$£¥]', '', value_str)

        # Handle negative indicators (parentheses or minus)
        is_negative = False
        if value_str.startswith('(') and value_str.endswith(')'):
            is_negative = True
            value_str = value_str[1:-1].strip()
        elif value_str.startswith('-'):
            is_negative = True
            value_str = value_str[1:].strip()

        # Convert comma decimal to dot
        # Check if it's a comma decimal (e.g., "1,234.56" vs "1.234,56")
        if ',' in value_str and '.' in value_str:
            # Determine format: if comma before dot, it's thousands separator
            comma_pos = value_str.find(',')
            dot_pos = value_str.find('.')
            if comma_pos < dot_pos:
                # Format: "1,234.56" -> remove comma
                value_str = value_str.replace(',', '')
            else:
                # Format: "1.234,56" -> swap comma and dot
                value_str = value_str.replace('.', '').replace(',', '.')
        elif ',' in value_str:
            # Might be decimal separator (European format)
            # If only one comma and it's in last 3 chars, treat as decimal
            if len(value_str.split(',')) == 2 and len(value_str.split(',')[1]) <= 2:
                value_str = value_str.replace(',', '.')
            else:
                # Otherwise treat as thousands separator
                value_str = value_str.replace(',', '')

        try:
            result = float(value_str)
            return -result if is_negative else result
        except ValueError:
            return 0.0

    @classmethod
    def validate_critical_columns(cls, mapping: Dict[str, str], report_type: str) -> List[str]:
        """
        Validate that critical columns are present

        Returns list of missing critical columns
        """
        missing = []

        if report_type == "transactions":
            critical = ["date", "sku", "qty"]
            for field in critical:
                if field not in mapping:
                    missing.append(field)

        elif report_type == "products":
            critical = ["sku"]
            for field in critical:
                if field not in mapping:
                    missing.append(field)

        return missing
