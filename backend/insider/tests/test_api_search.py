import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import logging
import urllib.parse

from insider.models import Incidence


class IncidenceSearchTests(APITestCase):
    databases = '__all__'

    def setUp(self):
        # Create a mock staff user
        self.staff_user = User.objects.create_user(
            username='staff', 
            password='password123',
            is_staff=True
        )
        self.client.force_authenticate(user=self.staff_user)
        
        # Base datetime for consistent testing
        self.base_time = timezone.now()
        
        # Create different varieties of incidences for filtering
        self.incidence1 = Incidence.objects.create(
            title="SyntaxError: Invalid syntax in parser",
            fingerprint="abc123hash",
            status="OPEN",
            occurrence_count=5
        )
        # Override first_seen and last_seen via update to bypass auto_now properties
        Incidence.objects.filter(id=self.incidence1.id).update(
            first_seen=self.base_time - timedelta(days=10),
            last_seen=self.base_time - timedelta(days=2)
        )
        
        self.incidence2 = Incidence.objects.create(
            title="Database Connection Error",
            fingerprint="def456hash",
            status="RESOLVED",
            occurrence_count=1
        )
        Incidence.objects.filter(id=self.incidence2.id).update(
            first_seen=self.base_time - timedelta(days=5),
            last_seen=self.base_time - timedelta(days=1)
        )
        
        self.incidence3 = Incidence.objects.create(
            title="OperationalError: server closed the connection",
            fingerprint="ghi789hash",
            status="OPEN",
            occurrence_count=10
        )
        Incidence.objects.filter(id=self.incidence3.id).update(
            first_seen=self.base_time - timedelta(days=3),
            last_seen=self.base_time
        )
        
        # Base URL for incidences (assuming standard router)
        self.url = reverse('incidence-list')
        
    def test_search_by_title_partial_match(self):
        """Test partial case-insensitive title search."""
        response = self.client.get(f"{self.url}?q=error")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3) # All have 'error' / 'Error'
        
        response = self.client.get(f"{self.url}?q=database")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.incidence2.id)
        
    def test_search_by_exact_fingerprint(self):
        """Test exact fingerprint search."""
        response = self.client.get(f"{self.url}?fingerprint=def456hash")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.incidence2.id)
        
        # Partial fingerprint should NOT match based on our implementation
        response = self.client.get(f"{self.url}?fingerprint=def456")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)
        
    def test_filter_by_valid_status(self):
        """Test status filtering with valid choices."""
        response = self.client.get(f"{self.url}?status=OPEN")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        
        response = self.client.get(f"{self.url}?status=RESOLVED")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.incidence2.id)
        
    def test_filter_by_invalid_status_raises_400(self):
        """Ensure invalid status gracefully returns 400 Bad Request."""
        response = self.client.get(f"{self.url}?status=INVALID_STATUS")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid status", str(response.data))
        
    def test_filter_by_first_seen_date_range(self):
        """Test first_seen bounds."""
        from_str = urllib.parse.quote((self.base_time - timedelta(days=6)).isoformat())
        to_str = urllib.parse.quote((self.base_time - timedelta(days=4)).isoformat())
        
        response = self.client.get(f"{self.url}?first_seen_from={from_str}&first_seen_to={to_str}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.incidence2.id)
        
    def test_filter_by_last_seen_date_range(self):
        """Test last_seen bounds."""
        from_str = urllib.parse.quote((self.base_time - timedelta(days=1, hours=12)).isoformat()) # 1.5 days ago
        
        response = self.client.get(f"{self.url}?last_seen_from={from_str}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2) # incidence2 (1 day ago) and incidence3 (0 days ago)
        
    def test_combined_filters(self):
        """Ensure multiple filters stack correctly."""
        from_str = urllib.parse.quote((self.base_time - timedelta(days=12)).isoformat())
        
        query = f"?status=OPEN&q=syntax&first_seen_from={from_str}"
        response = self.client.get(f"{self.url}{query}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.incidence1.id)

    def test_filter_by_invalid_date_raises_400(self):
        """Ensure invalid dates return 400 Bad Request."""
        response = self.client.get(f"{self.url}?first_seen_from=invalid-date")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid datetime format", str(response.data))
