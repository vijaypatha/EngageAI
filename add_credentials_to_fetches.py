#!/usr/bin/env python3
# Objective: Add `credentials: 'include'` to all `fetch` calls in
# `frontend/src/app/copilot/[business_name]/page.tsx` that target the backend API.
# Version 2: Using targeted string replacements for known fetch call structures.

import sys

filepath = "frontend/src/app/copilot/[business_name]/page.tsx"

try:
    with open(filepath, "r") as f:
        content = f.read()
except FileNotFoundError:
    print(f"Error: File not found at {filepath}")
    sys.exit(1)

original_content_hash = hash(content)

# 1. fetchNudges:
# Example before: fetch(API_BASE_URL + '/ai-nudge-copilot/nudges')
# Example after: fetch(API_BASE_URL + '/ai-nudge-copilot/nudges', { credentials: 'include' })
# This specific one was changed to use string concatenation by a previous script.
content = content.replace(
    "fetch(API_BASE_URL + '/ai-nudge-copilot/nudges')",
    "fetch(API_BASE_URL + '/ai-nudge-copilot/nudges', { credentials: 'include' })"
)

# 2. fetchBusinessDetails:
# Example before: fetch(`${API_BASE_URL}/business-profile/navigation-profile/slug/${businessSlug}`)
# Example after: fetch(`${API_BASE_URL}/business-profile/navigation-profile/slug/${businessSlug}`, { credentials: 'include' })
content = content.replace(
    "fetch(`${API_BASE_URL}/business-profile/navigation-profile/slug/${businessSlug}`)",
    "fetch(`${API_BASE_URL}/business-profile/navigation-profile/slug/${businessSlug}`, { credentials: 'include' })"
)

# 3. handleDismiss (used by ActionCenter and SentimentSection):
# Example before: fetch(`${API_BASE_URL}/ai-nudge-copilot/nudges/${nudgeId}/dismiss`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) })
# Example after: fetch(`${API_BASE_URL}/ai-nudge-copilot/nudges/${nudgeId}/dismiss`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}), credentials: 'include' })
content = content.replace(
    "fetch(`${API_BASE_URL}/ai-nudge-copilot/nudges/${nudgeId}/dismiss`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) })",
    "fetch(`${API_BASE_URL}/ai-nudge-copilot/nudges/${nudgeId}/dismiss`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}), credentials: 'include' })"
)

# 4. handleActivatePlan:
# Example before: fetch(`${API_BASE_URL}/follow-up-plans/activate-from-nudge/${nudgeId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ customer_id: customerId, messages: finalMessages }) })
# Example after: fetch(`${API_BASE_URL}/follow-up-plans/activate-from-nudge/${nudgeId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ customer_id: customerId, messages: finalMessages }), credentials: 'include' })
content = content.replace(
    "fetch(`${API_BASE_URL}/follow-up-plans/activate-from-nudge/${nudgeId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ customer_id: customerId, messages: finalMessages }) })",
    "fetch(`${API_BASE_URL}/follow-up-plans/activate-from-nudge/${nudgeId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ customer_id: customerId, messages: finalMessages }), credentials: 'include' })"
)

# 5. handleConfirmEvent:
# Example before: fetch(`${API_BASE_URL}/targeted-events/confirm-from-nudge/${nudgeId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmed_datetime_utc: confirmedDatetimeUtc, confirmed_purpose: confirmedPurpose }) })
# Example after: fetch(`${API_BASE_URL}/targeted-events/confirm-from-nudge/${nudgeId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmed_datetime_utc: confirmedDatetimeUtc, confirmed_purpose: confirmedPurpose }), credentials: 'include' })
content = content.replace(
    "fetch(`${API_BASE_URL}/targeted-events/confirm-from-nudge/${nudgeId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmed_datetime_utc: confirmedDatetimeUtc, confirmed_purpose: confirmedPurpose }) })",
    "fetch(`${API_BASE_URL}/targeted-events/confirm-from-nudge/${nudgeId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmed_datetime_utc: confirmedDatetimeUtc, confirmed_purpose: confirmedPurpose }), credentials: 'include' })"
)

# 6. handleLaunchGrowthCampaign:
# Example before: fetch(`${API_BASE_URL}/copilot-growth/nudges/${nudgeId}/launch-campaign`, { method: 'POST' })
# Example after: fetch(`${API_BASE_URL}/copilot-growth/nudges/${nudgeId}/launch-campaign`, { method: 'POST', credentials: 'include' })
content = content.replace(
    "fetch(`${API_BASE_URL}/copilot-growth/nudges/${nudgeId}/launch-campaign`, { method: 'POST' })",
    "fetch(`${API_BASE_URL}/copilot-growth/nudges/${nudgeId}/launch-campaign`, { method: 'POST', credentials: 'include' })"
)


if hash(content) != original_content_hash:
    try:
        with open(filepath, "w") as f:
            f.write(content)
        print(f"Successfully added `credentials: 'include'` to fetch calls in {filepath} using targeted replacements.")
    except Exception as e:
        print(f"Error writing updated content to {filepath}: {e}")
        sys.exit(1)
else:
    print(f"No changes made to {filepath} as fetch calls might already include credentials or patterns didn't match.")
