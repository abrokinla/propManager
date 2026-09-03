"""
AI Service — Property description and social post generation using Groq API.
"""
import json
import logging
import urllib.request
from django.conf import settings

logger = logging.getLogger(__name__)

GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'


def _groq_chat(messages, model='llama-3.3-70b-versatile', temperature=0.7, max_tokens=1024):
    """Make a request to the Groq API."""
    api_key = settings.GROQ_API_KEY
    if not api_key:
        logger.warning('[AI] GROQ_API_KEY not configured')
        return None

    payload = json.dumps({
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }).encode()

    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        body = json.loads(resp.read().decode())
        return body['choices'][0]['message']['content']
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        logger.error(f'Groq API error {e.code}: {body}')
        return None
    except Exception as e:
        logger.error(f'Groq API error: {e}')
        return None


def generate_property_description(property_data):
    """
    Generate a professional property listing description.

    property_data should contain:
      - name, property_type, address, description (existing, may be empty)
      - total_units, amenities (comma-separated), nearby_places (comma-separated)
      - units: list of { unit_number, bedrooms, bathrooms, toilets, size_sqft, price_rent, rent_cycle }
    """
    units_info = ''
    for u in property_data.get('units', []):
        parts = [f"Unit {u.get('unit_number', '?')}"]
        if u.get('bedrooms'): parts.append(f"{u['bedrooms']} bedroom(s)")
        if u.get('bathrooms'): parts.append(f"{u['bathrooms']} bathroom(s)")
        if u.get('toilets'): parts.append(f"{u['toilets']} toilet(s)")
        if u.get('size_sqft'): parts.append(f"{u['size_sqft']} sqft")
        if u.get('price_rent'): parts.append(f"₦{u['price_rent']:,.0f}/{u.get('rent_cycle', 'year')}")
        units_info += '- ' + ', '.join(parts) + '\n'

    prompt = f"""You are a professional real estate copywriter. Write a compelling property listing description for the following property. Be persuasive, highlight key selling points, and keep it between 150-250 words. Do not use headings or bullet points — write it as a flowing paragraph.

Property Name: {property_data.get('name', 'N/A')}
Type: {property_data.get('property_type', 'N/A')}
Address: {property_data.get('address', 'N/A')}
Existing Description: {property_data.get('description', '') or 'None provided'}
Total Units: {property_data.get('total_units', 'N/A')}
Amenities: {property_data.get('amenities', '') or 'None listed'}
Nearby Places: {property_data.get('nearby_places', '') or 'None listed'}

Units:
{units_info or 'No unit details available.'}

Write only the description text, nothing else."""

    messages = [
        {'role': 'system', 'content': 'You are a professional real estate copywriter specializing in property listings.'},
        {'role': 'user', 'content': prompt},
    ]

    return _groq_chat(messages, temperature=0.7, max_tokens=512)


def generate_social_posts(property_data, platform='all'):
    """
    Generate social media posts for a property listing.

    platform: 'instagram', 'twitter', 'whatsapp', or 'all' (returns all three)
    """
    units_summary = ''
    for u in property_data.get('units', [])[:5]:
        if u.get('price_rent'):
            units_summary += f"- Unit {u.get('unit_number', '?')}: {u.get('bedrooms', '?')}BR, ₦{u['price_rent']:,.0f}/{u.get('rent_cycle', 'yr')}\n"

    prompt = f"""Generate social media posts for this property listing. Create posts for the following platforms:

Property: {property_data.get('name', 'N/A')}
Type: {property_data.get('property_type', 'N/A')}
Address: {property_data.get('address', 'N/A')}
Amenities: {property_data.get('amenities', '') or 'N/A'}
Available Units:
{units_summary or 'Contact for availability'}

Generate posts in this exact JSON format (no markdown, just raw JSON):
{{
  "instagram": "post text with emojis and hashtags for Instagram, 2-3 paragraphs, engaging and visual",
  "twitter": "concise tweet-style post under 280 chars with emojis and 2-3 hashtags",
  "whatsapp": "short, professional broadcast message, no emojis, clear and to the point"
}}

Return ONLY the JSON object, no other text."""

    messages = [
        {'role': 'system', 'content': 'You are a social media manager for a real estate company. Generate engaging, platform-appropriate content.'},
        {'role': 'user', 'content': prompt},
    ]

    result = _groq_chat(messages, temperature=0.8, max_tokens=800)
    if not result:
        return None

    # Try to parse JSON from the response
    try:
        # Strip markdown code fences if present
        cleaned = result.strip()
        if cleaned.startswith('```'):
            cleaned = cleaned.split('\n', 1)[1]
        if cleaned.endswith('```'):
            cleaned = cleaned.rsplit('```', 1)[0]
        cleaned = cleaned.strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error(f'Failed to parse AI response as JSON: {result[:200]}')
        return {'raw': result}
