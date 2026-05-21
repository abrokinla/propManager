from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from properties.models import Property, Unit, Tenant, Payment, MaintenanceRequest
from datetime import date, timedelta


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_success(self):
        response = self.client.post('/api/register/', {
            'username': 'newuser',
            'email': 'new@test.com',
            'password': 'strongpass123',
            'first_name': 'New',
            'last_name': 'User',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username='newuser').exists())
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_register_duplicate_username(self):
        User.objects.create_user(username='existing', password='pass12345')
        response = self.client.post('/api/register/', {
            'username': 'existing',
            'email': 'other@test.com',
            'password': 'strongpass123',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_short_password(self):
        response = self.client.post('/api/register/', {
            'username': 'newuser',
            'email': 'new@test.com',
            'password': 'short',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_success(self):
        User.objects.create_user(username='testuser', password='testpass123')
        response = self.client.post('/api/login/', {
            'username': 'testuser',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_login_wrong_password(self):
        User.objects.create_user(username='testuser', password='testpass123')
        response = self.client.post('/api/login/', {
            'username': 'testuser',
            'password': 'wrongpass',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_nonexistent_user(self):
        response = self.client.post('/api/login/', {
            'username': 'nobody',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ProfileTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='profileuser', password='testpass123')

    def test_get_profile_authenticated(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/profile/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'profileuser')

    def test_get_profile_unauthenticated(self):
        response = self.client.get('/api/profile/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_profile_role(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.put('/api/profile/', {'role': 'manager'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.role, 'manager')


class MultiUserIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user(username='owner1', password='pass12345')
        self.user2 = User.objects.create_user(username='owner2', password='pass12345')
        self.prop1 = Property.objects.create(
            name='Property 1', address='Addr 1', property_type='Apartment', owner=self.user1
        )
        self.prop2 = Property.objects.create(
            name='Property 2', address='Addr 2', property_type='House', owner=self.user2
        )

    def test_user1_sees_only_own_properties(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get('/api/properties/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['name'], 'Property 1')

    def test_user2_sees_only_own_properties(self):
        self.client.force_authenticate(user=self.user2)
        response = self.client.get('/api/properties/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['name'], 'Property 2')

    def test_user1_cannot_see_user2_property_detail(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(f'/api/properties/{self.prop2.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_dashboard_stats_per_user(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get('/api/dashboard/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_properties'], 1)


class PropertyCRUDTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='cruduser', password='testpass123')
        self.client.force_authenticate(user=self.user)

    def test_create_property(self):
        response = self.client.post('/api/properties/', {
            'name': 'My Property',
            'address': '123 Main St',
            'property_type': 'Apartment',
            'description': 'A nice place',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['owner']['username'], 'cruduser')

    def test_list_properties(self):
        Property.objects.create(name='P1', address='A1', property_type='House', owner=self.user)
        Property.objects.create(name='P2', address='A2', property_type='Condo', owner=self.user)
        response = self.client.get('/api/properties/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)

    def test_delete_property(self):
        prop = Property.objects.create(name='ToDelete', address='A1', property_type='House', owner=self.user)
        response = self.client.delete(f'/api/properties/{prop.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Property.objects.filter(id=prop.id).exists())


class UserProfileSignalTests(TestCase):
    def test_profile_created_on_user_creation(self):
        user = User.objects.create_user(username='signaltest', password='pass12345')
        self.assertTrue(hasattr(user, 'profile'))
        self.assertEqual(user.profile.role, 'owner')
