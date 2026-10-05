"""Agent CRM endpoints: profile, KYC submission, lead inbox, stats.

KYC gating: ``pending`` agents get one property and no public profile;
``verified`` agents unlock the public profile at /agents/<slug> and the full
CRM. Gating is enforced in helpers here rather than sprinkled through views.
"""
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone as dj_timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from properties.models import Property, PropertyView, VisitBooking
from workspaces.models import AgentKYC, Organization
from workspaces.scopes import accessible_properties, organizations_for
from workspaces.serializers import AgentKYCSerializer, AgentProfileSerializer

PENDING_PROPERTY_LIMIT = 1


def get_agent_org(user):
    """The user's agent-track organization, or None."""
    return organizations_for(user).filter(track='agent').first()


def kyc_status(user):
    """Read KYC status from the database.

    Deliberately not ``user.kyc``: the reverse one-to-one accessor caches, and
    provisioning populates that cache while the record is still 'unsubmitted'.
    A user who verifies later in the same process would keep reading the stale
    value. One extra query beats an entitlement check lying about the user.
    """
    status_ = (
        AgentKYC.objects.filter(user=user)
        .values_list('status', flat=True)
        .first()
    )
    return status_ or 'unsubmitted'


def is_verified(user):
    return kyc_status(user) == 'verified'


def public_agent_slug(user):
    return user.profile.agent_public_slug


class AgentProfileView(APIView):
    """GET/PUT the current agent's public profile."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        org = get_agent_org(request.user)
        if org is None:
            return Response({'detail': 'No agent workspace found.'}, status=404)
        data = AgentProfileSerializer(org).data
        data['kyc_status'] = kyc_status(request.user)
        data['agent_slug'] = public_agent_slug(request.user)
        data['verified'] = is_verified(request.user)
        return Response(data)

    def put(self, request):
        org = get_agent_org(request.user)
        if org is None:
            return Response({'detail': 'No agent workspace found.'}, status=404)
        serializer = AgentProfileSerializer(org, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


class AgentKYCView(APIView):
    """GET current KYC status, POST documents for review."""

    permission_classes = [IsAuthenticated]
    serializer_class = AgentKYCSerializer

    def get_kyc(self, user):
        kyc, _ = AgentKYC.objects.get_or_create(user=user)
        return kyc

    def get(self, request):
        kyc = self.get_kyc(request.user)
        return Response(self.serializer_class(kyc).data)

    def post(self, request):
        kyc = self.get_kyc(request.user)
        if kyc.status == 'verified':
            return Response(
                {'detail': 'Your KYC is already verified.'}, status=400
            )
        if kyc.status == 'pending':
            return Response(
                {'detail': 'Your KYC is already under review.'}, status=400
            )
        serializer = self.serializer_class(kyc, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save(status='pending', rejection_reason='')
            return Response(self.serializer_class(kyc).data, status=200)
        return Response(serializer.errors, status=400)


class AgentPublicProfileView(APIView):
    """Public agent profile at /api/public/agents/<slug>/."""

    permission_classes = [AllowAny]

    def get(self, request, slug):
        user = (
            AgentKYC.objects.filter(
                user__profile__agent_public_slug=slug, status='verified'
            )
            .select_related('user')
            .first()
        )
        if user is None:
            return Response({'detail': 'Agent not found.'}, status=404)
        org = get_agent_org(user.user)
        if org is None:
            return Response({'detail': 'Agent not found.'}, status=404)
        data = AgentProfileSerializer(org).data
        data['first_name'] = user.user.first_name
        data['last_name'] = user.user.last_name
        data['verified'] = True
        return Response(data)


class AgentPropertyListView(APIView):
    """Published listings for a public agent profile."""

    permission_classes = [AllowAny]

    def get(self, request, slug):
        kyc = AgentKYC.objects.filter(
            user__profile__agent_public_slug=slug, status='verified'
        ).select_related('user').first()
        if kyc is None:
            return Response({'detail': 'Agent not found.'}, status=404)
        org = get_agent_org(kyc.user)
        if org is None:
            return Response({'detail': 'Agent not found.'}, status=404)
        props = org.properties.filter(is_published=True)
        return Response([
            {
                'id': p.id,
                'name': p.name,
                'address': p.address,
                'property_type': p.property_type,
                'image_url': p.image_url,
                'price_rent': str(p.price_rent) if hasattr(p, 'price_rent') else None,
                'public_slug': p.public_slug,
            }
            for p in props
        ])


class AgentLeadsView(APIView):
    """Lead inbox: bookings and listing views across the agent's properties."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        props = accessible_properties(request.user)
        bookings = VisitBooking.objects.filter(
            property__in=props
        ).select_related('property').order_by('-created_at')[:100]

        since = dj_timezone.now() - dj_timezone.timedelta(days=30)
        views = PropertyView.objects.filter(
            property__in=props, viewed_at__gte=since
        )

        return Response({
            'bookings': [
                {
                    'id': b.id,
                    'property_id': b.property_id,
                    'property_name': b.property.name,
                    'guest_name': b.guest_name,
                    'guest_email': b.guest_email,
                    'guest_phone': b.guest_phone,
                    'visit_date': b.visit_date,
                    'status': b.status,
                    'created_at': b.created_at,
                }
                for b in bookings
            ],
            'view_count': views.count(),
            'views_by_property': list(
                views.values('property__name')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
        })


class AgentStatsView(APIView):
    """Headline numbers for the agent dashboard."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        props = accessible_properties(request.user)
        since = dj_timezone.now() - dj_timezone.timedelta(days=30)
        views = PropertyView.objects.filter(
            property__in=props, viewed_at__gte=since
        )
        bookings = VisitBooking.objects.filter(property__in=props)
        published = props.filter(is_published=True)

        return Response({
            'total_properties': props.count(),
            'published_properties': published.count(),
            'view_count': views.count(),
            'booking_count': bookings.count(),
            'pending_bookings': bookings.filter(status='pending').count(),
            'confirmed_bookings': bookings.filter(status='confirmed').count(),
            'kyc_status': kyc_status(request.user),
            'property_limit': self._limit(request.user),
        })

    def _limit(self, user):
        from workspaces.plans import get_limit
        from workspaces.services.provisioning import get_subscription

        sub = get_subscription(user)
        if not is_verified(user):
            return PENDING_PROPERTY_LIMIT
        return get_limit(sub.plan, 'properties', sub.limit_overrides)