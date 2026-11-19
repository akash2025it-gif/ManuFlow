from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError

from apps.accounts.models import CustomUser
from apps.master_data.models import (
    UnitOfMeasurement,
    UnitConversion,
    Supplier,
    Customer,
    RawMaterial,
    PackagingMaterial,
    Product,
    ProductPackSize,
    BillOfMaterials,
    BOMItem,
)


class MasterDataModelTests(TestCase):
    def setUp(self):
        self.kg = UnitOfMeasurement.objects.create(
            code='KG', name='Kilogram', uom_type=UnitOfMeasurement.UOMType.WEIGHT
        )
        self.g = UnitOfMeasurement.objects.create(
            code='G', name='Gram', uom_type=UnitOfMeasurement.UOMType.WEIGHT
        )
        self.litre = UnitOfMeasurement.objects.create(
            code='L', name='Litre', uom_type=UnitOfMeasurement.UOMType.VOLUME
        )
        self.pcs = UnitOfMeasurement.objects.create(
            code='PCS', name='Pieces', uom_type=UnitOfMeasurement.UOMType.COUNT
        )

        self.supplier = Supplier.objects.create(
            code='SUP-01',
            name='Test Chemical Corp',
            payment_terms='Net 30 Days'
        )

        self.customer = Customer.objects.create(
            code='CUST-01',
            name='Alpha Retailers',
            customer_type=Customer.CustomerType.RETAILER,
            credit_limit=Decimal('50000.00'),
            credit_days=30
        )

        self.raw_mat = RawMaterial.objects.create(
            code='RM-01',
            name='Polymer Resin',
            uom=self.kg,
            standard_cost=Decimal('120.00'),
            reorder_level=Decimal('50.00'),
            preferred_supplier=self.supplier
        )

        self.pkg_mat = PackagingMaterial.objects.create(
            code='PM-01',
            name='500ml Bottle',
            material_type=PackagingMaterial.MaterialType.BOTTLE,
            uom=self.pcs,
            standard_cost=Decimal('10.00')
        )

        self.product = Product.objects.create(
            code='PRD-01',
            name='Heavy Clean Solution',
            base_uom=self.litre
        )

    def test_uom_clean_and_conversion(self):
        conversion = UnitConversion(
            from_uom=self.kg,
            to_uom=self.g,
            multiplier=Decimal('1000.000000')
        )
        conversion.full_clean()
        conversion.save()
        self.assertEqual(str(conversion), "1 KG = 1000.000000 G")

        # Conversion to self must fail validation
        invalid_conv = UnitConversion(from_uom=self.kg, to_uom=self.kg, multiplier=Decimal('1.0'))
        with self.assertRaises(ValidationError):
            invalid_conv.clean()

    def test_product_pack_size(self):
        sku = ProductPackSize.objects.create(
            product=self.product,
            sku_code='SKU-PRD01-500ML',
            pack_name='500ml Pack',
            pack_size_value=Decimal('0.50'),
            uom=self.litre,
            primary_packaging=self.pkg_mat,
            mrp=Decimal('150.00'),
            retailer_price=Decimal('110.00'),
            distributor_price=Decimal('90.00')
        )
        self.assertEqual(self.product.pack_sizes.count(), 1)
        self.assertEqual(sku.product, self.product)
        self.assertEqual(sku.mrp, Decimal('150.00'))

    def test_bom_yield_and_costing(self):
        bom = BillOfMaterials.objects.create(
            product=self.product,
            bom_code='BOM-PRD01-V1',
            name='Formula Alpha',
            batch_size=Decimal('100.00'),
            output_uom=self.litre,
            expected_yield_pct=Decimal('95.00')
        )

        # Expected output = 100 * 95% = 95.00 Litres
        self.assertEqual(bom.expected_output_quantity, Decimal('95.00'))

        # Add 2 ingredients: 50 KG of RM-01 (@ 120/kg) and 100 PCS of PM-01 (@ 10/pcs)
        item1 = BOMItem.objects.create(
            bom=bom,
            item_type=BOMItem.ItemType.RAW_MATERIAL,
            raw_material=self.raw_mat,
            quantity=Decimal('50.0000'),
            uom=self.kg
        )
        item2 = BOMItem.objects.create(
            bom=bom,
            item_type=BOMItem.ItemType.PACKAGING_MATERIAL,
            packaging_material=self.pkg_mat,
            quantity=Decimal('100.0000'),
            uom=self.pcs
        )

        self.assertEqual(item1.line_cost, Decimal('6000.00'))  # 50 * 120
        self.assertEqual(item2.line_cost, Decimal('1000.00'))  # 100 * 10
        self.assertEqual(bom.total_estimated_cost, Decimal('7000.00'))
        # Cost per unit output = 7000 / 95 = 73.68
        self.assertEqual(bom.cost_per_unit_output, (Decimal('7000.00') / Decimal('95.00')).quantize(Decimal('0.01')))

    def test_bom_validation(self):
        invalid_bom = BillOfMaterials(
            product=self.product,
            bom_code='BOM-INVALID',
            name='Invalid Yield',
            batch_size=Decimal('100.00'),
            output_uom=self.litre,
            expected_yield_pct=Decimal('105.00')  # > 100%
        )
        with self.assertRaises(ValidationError):
            invalid_bom.clean()


class MasterDataRolePermissionsAndCRUDTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = 'Pass12345!'

        # Roles
        self.admin = CustomUser.objects.create_user(
            email='admin@nit.edu', username='admin_user', password=self.password,
            role=CustomUser.Role.ADMIN, is_staff=True
        )
        self.salesman = CustomUser.objects.create_user(
            email='sales@nit.edu', username='sales_user', password=self.password,
            role=CustomUser.Role.SALESMAN
        )
        self.production = CustomUser.objects.create_user(
            email='prod@nit.edu', username='prod_user', password=self.password,
            role=CustomUser.Role.PRODUCTION
        )
        self.auditor = CustomUser.objects.create_user(
            email='auditor@nit.edu', username='auditor_user', password=self.password,
            role=CustomUser.Role.AUDITOR
        )
        self.owner = CustomUser.objects.create_user(
            email='owner@nit.edu', username='owner_user', password=self.password,
            role=CustomUser.Role.OWNER
        )

        # UOM
        self.uom_l = UnitOfMeasurement.objects.create(code='L', name='Litre', uom_type='VOLUME')
        self.uom_kg = UnitOfMeasurement.objects.create(code='KG', name='Kilogram', uom_type='WEIGHT')

        # Product
        self.product = Product.objects.create(code='PRD-T1', name='Industrial Cleanser', base_uom=self.uom_l)

        # Customer
        self.customer = Customer.objects.create(
            code='CUST-T1', name='South Traders', customer_type=Customer.CustomerType.DISTRIBUTOR,
            credit_limit=Decimal('100000.00')
        )

    def test_master_data_hub_access(self):
        # Unauthenticated -> redirect to login
        response = self.client.get(reverse('master_data_hub'))
        self.assertEqual(response.status_code, 302)

        # Authenticated salesman can view hub
        self.client.login(username='sales_user', password=self.password)
        res = self.client.get(reverse('master_data_hub'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Master Data Management Suite")

    def test_salesman_cannot_modify_product_or_bom(self):
        self.client.login(username='sales_user', password=self.password)

        # Salesman GET on product_create -> 403 Forbidden
        res = self.client.get(reverse('product_create'))
        self.assertEqual(res.status_code, 403)

        # Salesman GET on bom_create -> 403 Forbidden
        res = self.client.get(reverse('bom_create'))
        self.assertEqual(res.status_code, 403)

    def test_salesman_can_create_customer(self):
        self.client.login(username='sales_user', password=self.password)

        res = self.client.post(reverse('customer_create'), {
            'code': 'CUST-NEW-99',
            'name': 'New Retail Store',
            'customer_type': 'RETAILER',
            'credit_limit': '25000.00',
            'credit_days': 15,
            'is_active': True,
        })
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Customer.objects.filter(code='CUST-NEW-99').exists())

    def test_production_cannot_modify_customer(self):
        self.client.login(username='prod_user', password=self.password)

        # Production GET on customer_create -> 403 Forbidden
        res = self.client.get(reverse('customer_create'))
        self.assertEqual(res.status_code, 403)

    def test_production_can_create_product(self):
        self.client.login(username='prod_user', password=self.password)

        res = self.client.post(reverse('product_create'), {
            'code': 'PRD-NEW-50',
            'name': 'New Machine Degreaser',
            'category': 'Specialty Cleaners',
            'base_uom': self.uom_l.pk,
            'is_active': True,
        })
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Product.objects.filter(code='PRD-NEW-50').exists())

    def test_auditor_read_only_protection(self):
        self.client.login(username='auditor_user', password=self.password)

        # Auditor can view product detail
        res = self.client.get(reverse('product_detail', kwargs={'pk': self.product.pk}))
        self.assertEqual(res.status_code, 200)

        # Auditor cannot delete or edit product -> 403
        res = self.client.get(reverse('product_update', kwargs={'pk': self.product.pk}))
        self.assertEqual(res.status_code, 403)

        res = self.client.get(reverse('product_delete', kwargs={'pk': self.product.pk}))
        self.assertEqual(res.status_code, 403)

    def test_search_and_filters(self):
        self.client.login(username='admin_user', password=self.password)

        # Search product by code
        res = self.client.get(reverse('product_list') + '?q=PRD-T1')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Industrial Cleanser")

        # Search customer by name
        res = self.client.get(reverse('customer_list') + '?q=South')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "South Traders")
